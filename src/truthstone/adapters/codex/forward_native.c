/*
 * The Codex plugin's native forwarder: stdin -> Truthstone daemon (POST /hook/codex) -> stdout.
 *
 * A C port of forward.py, which stays the specification: tests/test_codex_native.py holds the
 * two to identical requests and byte-identical output. Codex runs every hook as a new process,
 * and after the model's thinking pause the machine is cold: starting Python then costs 35-40
 * ms, starting a small C program a few. At SessionStart the runtime compiles this file
 * (native.py) into $PLUGIN_DATA/lean/forward-native, and the plugin launcher prefers it for the
 * events that only forward, then the Python forwarder, then the runtime.
 *
 * forward.py's rules:
 *   - the home: TRUTHSTONE_HOME (or a former name's), else ~/.truthstone (or a former name's
 *     directory while only that exists), through links only root or this user could have
 *     placed (daemon/private_paths.py, R11);
 *   - daemon.json: never through a symlink, at most 64,000 bytes, JSON as Python reads it;
 *   - the daemon: IPv4 loopback only, a port in range, a sane token, a PID that is alive;
 *   - one POST /hook/codex. Only a 200 counts, never a chunked reply, at most 256,000 bytes;
 *   - the reply is data: it is validated as Python's json validates it, scanned only for a
 *     grant (hookSpecificOutput.permissionDecision "allow", or decision "approve"), and then
 *     written out byte for byte, or not at all;
 *   - stdin is read up to 1,000,000 bytes; --timeout seconds (default 4) bounds the connect,
 *     the send and each read, as Python's socket timeout does;
 *   - TRUTHSTONE_DISABLE means print nothing;
 *   - every path exits 0. Codex reads exit code 2 as "block this tool call".
 *
 * Deliberately stricter, failing open where forward.py would carry on: a host that inet_pton
 * cannot read is refused (Python's socket tries inet_pton first too, then the resolver), a FIFO
 * named daemon.json is not waited on, JSON nested deeper than 9,000 levels is refused (CPython
 * 3.12 and 3.13 refuse about 10,000), a --timeout written with digit-group underscores falls back
 * to the default, and a home spelled through a missing directory and ".." is not found.
 *
 * No shell and no heap: fixed buffers, every bound checked. No path from the environment but
 * the home's (TRUTHSTONE_HOME and HOME, former names included).
 */

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <pwd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif
#ifndef S_ISVTX
#define S_ISVTX 01000
#endif

#define MAX_STDIN 1000000   /* forward.MAX_STDIN_BYTES */
#define MAX_RESPONSE 256000 /* forward.MAX_RESPONSE_BYTES */
#define MAX_HANDSHAKE 64000 /* forward.read_handshake */
#define DEFAULT_TIMEOUT 4.0 /* forward.DEFAULT_TIMEOUT_S */
#define MAX_TIMEOUT 60.0
#define MAX_DEPTH 9000
#define MAX_INT_DIGITS 4300 /* CPython's int_max_str_digits: a longer integer is a ValueError */
#define PATH_CAP 4096
#define HEAD_CAP (MAX_HANDSHAKE + 512) /* the request line and headers, token included */
#define COUNT(a) (sizeof(a) / sizeof((a)[0]))

/* The product's settings prefix and data directory, then each former name's, newest first:
 * names.UPPER and names.SLUG, then names.FORMER. tests/test_codex_native.py keeps them equal. */
static const char *const PREFIXES[] = {
    "TRUTHSTONE",
    /* rename-tool: keep-begin native-former-names */
    "AGENTGUARD",
    /* rename-tool: keep-end */
};
static const char *const HOMES[] = {
    "~/.truthstone",
    /* rename-tool: keep-begin native-former-names */
    "~/.agentguard",
    /* rename-tool: keep-end */
};

/* ---- small helpers ------------------------------------------------------------------------ */

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

/* out = a[0:alen] + b; 0 when it does not fit. */
static int concat(char *out, size_t cap, const char *a, size_t alen, const char *b) {
    size_t blen = strlen(b);
    if (alen >= cap || blen >= cap - alen) return 0;
    memmove(out, a, alen);
    memcpy(out + alen, b, blen + 1);
    return 1;
}

/* Up to cap bytes from fd, to EOF; the count, or -1 on a read error. */
static ssize_t read_all(int fd, unsigned char *buf, size_t cap) {
    size_t got = 0;
    while (got < cap) {
        ssize_t n = read(fd, buf + got, cap - got);
        if (n == 0) break;
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        got += (size_t)n;
    }
    return (ssize_t)got;
}

static void write_all(int fd, const unsigned char *p, size_t n) {
    while (n > 0) {
        ssize_t w = write(fd, p, n);
        if (w < 0) {
            if (errno == EINTR) continue;
            return;
        }
        p += w;
        n -= (size_t)w;
    }
}

/* bytes.isspace(): what bytes.strip() and bytes.split() remove. */
static int byte_space(unsigned char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == 0x0b || c == 0x0c;
}

/* Python's str.isspace() at the start of p (n bytes of UTF-8): the character's length, or 0. */
static size_t space_at(const unsigned char *p, size_t n) {
    if (n >= 1 && ((p[0] >= 0x09 && p[0] <= 0x0d) || (p[0] >= 0x1c && p[0] <= 0x20))) return 1;
    if (n >= 2 && p[0] == 0xc2 && (p[1] == 0x85 || p[1] == 0xa0)) return 2;
    if (n < 3) return 0;
    if (p[0] == 0xe1 && p[1] == 0x9a && p[2] == 0x80) return 3; /* U+1680 */
    if (p[0] == 0xe2 && p[1] == 0x80 && ((p[2] >= 0x80 && p[2] <= 0x8a) || p[2] == 0xa8 || p[2] == 0xa9 ||
                                         p[2] == 0xaf))
        return 3; /* U+2000-U+200A, U+2028, U+2029, U+202F */
    if (p[0] == 0xe2 && p[1] == 0x81 && p[2] == 0x9f) return 3; /* U+205F */
    if (p[0] == 0xe3 && p[1] == 0x80 && p[2] == 0x80) return 3; /* U+3000 */
    return 0;
}

/* The same, for the character that ends p. */
static size_t space_before(const unsigned char *p, size_t n) {
    for (size_t k = 1; k <= 3 && k <= n; k++)
        if (space_at(p + n - k, k) == k) return k;
    return 0;
}

/* ---- settings and the home ------------------------------------------------------------------ */

/* forward.setting: TRUTHSTONE_<key>, else the same setting under a former name; NULL if unset. */
static const char *setting(const char *key) {
    char name[64];
    for (size_t i = 0; i < COUNT(PREFIXES); i++) {
        int n = snprintf(name, sizeof name, "%s_%s", PREFIXES[i], key);
        if (n < 0 || (size_t)n >= sizeof name) continue;
        const char *value = getenv(name);
        if (value != NULL && value[0] != '\0') return value;
    }
    return NULL;
}

/* forward.run's switch: setting("DISABLE").strip().lower() in ("1", "true", "yes", "on"). */
static int disabled(void) {
    static const char *const on[] = {"1", "true", "yes", "on"};
    const char *value = setting("DISABLE");
    if (value == NULL) return 0;
    const unsigned char *p = (const unsigned char *)value;
    size_t n = strlen(value), k;
    while (n > 0 && (k = space_at(p, n)) > 0) {
        p += k;
        n -= k;
    }
    while (n > 0 && (k = space_before(p, n)) > 0) n -= k;
    for (size_t i = 0; i < COUNT(on); i++) {
        if (strlen(on[i]) != n) continue;
        size_t j = 0;
        while (j < n && (p[j] >= 'A' && p[j] <= 'Z' ? p[j] + 32 : p[j]) == (unsigned char)on[i][j]) j++;
        if (j == n) return 1;
    }
    return 0;
}

/* posixpath.expanduser: a leading "~" or "~user" becomes that home, from $HOME or the password
 * database; anything else, or a user the database does not know, stays as it is. */
static int expanduser(const char *path, char *out, size_t cap) {
    if (path[0] != '~') return concat(out, cap, path, strlen(path), "");
    const char *rest = strchr(path + 1, '/');
    if (rest == NULL) rest = path + strlen(path);
    const char *home = NULL;
    if (rest == path + 1) {
        home = getenv("HOME");
        if (home == NULL) {
            struct passwd *pw = getpwuid(getuid());
            home = pw != NULL ? pw->pw_dir : NULL;
        }
    } else {
        char name[256];
        size_t n = (size_t)(rest - path - 1);
        if (n < sizeof name) {
            memcpy(name, path + 1, n);
            name[n] = '\0';
            struct passwd *pw = getpwnam(name);
            home = pw != NULL ? pw->pw_dir : NULL;
        }
    }
    if (home == NULL) return concat(out, cap, path, strlen(path), "");
    size_t h = strlen(home);
    while (h > 0 && home[h - 1] == '/') h--;
    if (h == 0 && *rest == '\0') return concat(out, cap, "/", 1, "");
    return concat(out, cap, home, h, rest);
}

/* private_paths.configured_home: the setting, else ~/.truthstone unless only a former name's
 * directory exists. */
static int configured_home(char *out, size_t cap) {
    struct stat st;
    const char *explicit_home = setting("HOME");
    if (explicit_home != NULL) return expanduser(explicit_home, out, cap);
    if (!expanduser(HOMES[0], out, cap)) return 0;
    if (lstat(out, &st) == 0) return 1;
    for (size_t i = 1; i < COUNT(HOMES); i++) {
        char candidate[PATH_CAP];
        if (expanduser(HOMES[i], candidate, sizeof candidate) && lstat(candidate, &st) == 0)
            return concat(out, cap, candidate, strlen(candidate), "");
    }
    return 1;
}

/* private_paths.trusted_home_link: a link that root or this user placed, in a directory nobody
 * else can change (owner-only, or sticky like /tmp). Its other clause, trusted_system_link
 * (root's link in a root-owned directory nobody else can write), is a case of this one. */
static int trusted_link(const char *link) {
    struct stat info, parent;
    char dir[PATH_CAP];
    const char *slash = strrchr(link, '/');
    size_t n = slash == link ? 1 : (size_t)(slash - link);
    if (lstat(link, &info) != 0 || n >= sizeof dir) return 0;
    memcpy(dir, link, n);
    dir[n] = '\0';
    if (stat(dir, &parent) != 0) return 0;
    uid_t me = getuid();
    if ((info.st_uid != 0 && info.st_uid != me) || (parent.st_uid != 0 && parent.st_uid != me)) return 0;
    return (parent.st_mode & 022) == 0 || (parent.st_mode & S_ISVTX) != 0;
}

/* private_paths.resolve_home: 1 and the home to read from in out; 0 when a link on the way is
 * one someone else could swap, or anything fails. macOS's /tmp and /var aliases are not links
 * here. */
static int resolve_home(const char *home, char *out, size_t cap) {
    char joined[PATH_CAP], absolute[PATH_CAP], current[PATH_CAP];
    if (home[0] == '/') {
        if (!concat(joined, sizeof joined, home, strlen(home), "")) return 0;
    } else {
        char cwd[PATH_CAP];
        if (getcwd(cwd, sizeof cwd) == NULL) return 0;
        size_t c = strlen(cwd);
        if (!concat(joined, sizeof joined, cwd, c, "/") || !concat(joined, sizeof joined, joined, c + 1, home))
            return 0;
    }
    /* "/" and the parts that are neither empty nor "." (".." stays: a link may come before it) */
    size_t len = 0;
    for (const char *part = joined; *part != '\0';) {
        const char *slash = strchr(part, '/');
        size_t n = slash != NULL ? (size_t)(slash - part) : strlen(part);
        if (n > 0 && !(n == 1 && part[0] == '.')) {
            if (len + 1 + n >= sizeof absolute) return 0;
            absolute[len++] = '/';
            memcpy(absolute + len, part, n);
            len += n;
        }
        part += n;
        if (*part == '/') part++;
    }
    if (len == 0) absolute[len++] = '/';
    absolute[len] = '\0';

    int linked = 0;
    memcpy(current, absolute, len + 1);
    for (;;) {
        struct stat st;
        if (lstat(current, &st) == 0 && S_ISLNK(st.st_mode) && strcmp(current, "/tmp") != 0 &&
            strcmp(current, "/var") != 0) {
            if (!trusted_link(current)) return 0;
            linked = 1;
        }
        char *slash = strrchr(current, '/');
        if (slash != current) {
            *slash = '\0';
        } else if (current[1] != '\0') {
            current[1] = '\0';
        } else {
            break;
        }
    }
    if (!linked) return concat(out, cap, home, strlen(home), "");
    char real[PATH_MAX];
    if (realpath(absolute, real) == NULL) return 0;
    return concat(out, cap, real, strlen(real), "");
}

/* forward.read_handshake: daemon.json from a trusted home, never through a symlink; its size,
 * or -1. */
static ssize_t read_handshake(unsigned char *buf) {
    char configured[PATH_CAP], home[PATH_CAP], path[PATH_CAP];
    if (!configured_home(configured, sizeof configured) || !resolve_home(configured, home, sizeof home))
        return -1;
    size_t h = strlen(home); /* os.path.join(home, "daemon.json") */
    if (!concat(path, sizeof path, home, h, h == 0 || home[h - 1] == '/' ? "daemon.json" : "/daemon.json"))
        return -1;
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t n = read_all(fd, buf, MAX_HANDSHAKE + 1);
    close(fd);
    return n > MAX_HANDSHAKE ? -1 : n;
}

/* ---- JSON, as forward.loads reads it -------------------------------------------------------- */

/* Python's strict UTF-8 decoder: no overlong forms, no surrogates, nothing above U+10FFFF. */
static int utf8_valid(const unsigned char *p, size_t n) {
    size_t i = 0;
    while (i < n) {
        unsigned char c = p[i];
        size_t need;
        unsigned char lo = 0x80, hi = 0xbf;
        if (c < 0x80) {
            i++;
            continue;
        }
        if (c >= 0xc2 && c <= 0xdf) need = 1;
        else if (c == 0xe0) need = 2, lo = 0xa0;
        else if (c == 0xed) need = 2, hi = 0x9f;
        else if (c >= 0xe1 && c <= 0xef) need = 2;
        else if (c == 0xf0) need = 3, lo = 0x90;
        else if (c == 0xf4) need = 3, hi = 0x8f;
        else if (c >= 0xf1 && c <= 0xf3) need = 3;
        else return 0;
        if (n - i - 1 < need || p[i + 1] < lo || p[i + 1] > hi) return 0;
        for (size_t k = 2; k <= need; k++)
            if (p[i + k] < 0x80 || p[i + k] > 0xbf) return 0;
        i += need + 1;
    }
    return 1;
}

enum { J_BAD, J_OBJECT, J_ARRAY, J_STRING, J_INT, J_OTHER };

/* A JSON value inside a document: [at, end) and its kind; at is NULL when absent. */
struct span {
    const unsigned char *at, *end;
    int kind;
};

/* Where a string's decoded text goes, when anyone wants it: its ASCII, while it fits. A
 * character above U+007F (a raw one, or an escape) clears ascii; no one here wants those. */
struct text {
    char *buf;
    size_t cap, len;
    int ascii;
};

static void put_char(struct text *t, unsigned long c) {
    if (t == NULL) return;
    if (c >= 0x80) {
        t->ascii = 0;
        return;
    }
    if (t->len < t->cap) t->buf[t->len] = (char)c;
    t->len++;
}

static int hex_digit(unsigned char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

/* A string at *p (on its opening quote), as json's scanstring reads it with strict=True: no raw
 * control characters, the eight short escapes and \uXXXX (lone surrogates included). Moves *p
 * past the closing quote; 0 when the string is not valid. */
static int scan_string(const unsigned char **p, const unsigned char *end, struct text *t) {
    const unsigned char *s = *p + 1;
    for (;;) {
        if (s >= end) return 0;
        unsigned long c = *s++;
        if (c == '"') break;
        if (c < 0x20) return 0;
        if (c == '\\') {
            if (s >= end) return 0;
            switch (c = *s++) {
            case '"': case '\\': case '/': break;
            case 'b': c = '\b'; break;
            case 'f': c = '\f'; break;
            case 'n': c = '\n'; break;
            case 'r': c = '\r'; break;
            case 't': c = '\t'; break;
            case 'u':
                if (end - s < 4) return 0;
                c = 0;
                for (int i = 0; i < 4; i++) {
                    int digit = hex_digit(*s++);
                    if (digit < 0) return 0;
                    c = c << 4 | (unsigned long)digit;
                }
                break;
            default: return 0;
            }
        }
        put_char(t, c);
    }
    *p = s;
    return 1;
}

static int is_digit(const unsigned char *s, const unsigned char *end) { return s < end && *s >= '0' && *s <= '9'; }

/* A number at *p, by json's grammar: J_INT or J_OTHER (a float), or J_BAD. CPython refuses an
 * integer of more than 4,300 digits; a float never fails. */
static int scan_number(const unsigned char **p, const unsigned char *end) {
    const unsigned char *s = *p, *digits;
    int kind = J_INT;
    if (s < end && *s == '-') s++;
    digits = s;
    if (s < end && *s == '0') {
        s++;
    } else if (s < end && *s >= '1' && *s <= '9') {
        while (is_digit(s, end)) s++;
    } else {
        return J_BAD;
    }
    size_t int_digits = (size_t)(s - digits);
    if (s < end && *s == '.') {
        if (!is_digit(s + 1, end)) return J_BAD;
        s += 2;
        while (is_digit(s, end)) s++;
        kind = J_OTHER;
    }
    if (s < end && (*s == 'e' || *s == 'E')) {
        s++;
        if (s < end && (*s == '+' || *s == '-')) s++;
        if (!is_digit(s, end)) return J_BAD;
        while (is_digit(s, end)) s++;
        kind = J_OTHER;
    }
    if (kind == J_INT && int_digits > MAX_INT_DIGITS) return J_BAD;
    *p = s;
    return kind;
}

static int literal(const unsigned char **p, const unsigned char *end, const char *word) {
    size_t n = strlen(word);
    if ((size_t)(end - *p) < n || memcmp(*p, word, n) != 0) return 0;
    *p += n;
    return 1;
}

static const unsigned char *skip_space(const unsigned char *s, const unsigned char *end) {
    while (s < end && (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r')) s++;
    return s;
}

/* One JSON document, as forward.loads reads it: one value (strict strings, NaN, Infinity and
 * -Infinity included) filling [p, p + n) bar surrounding whitespace. Returns its kind, or J_BAD.
 * When it is an object, *members counts its members and found[i] is the value of the last
 * member named keys[i]: Python keeps the last of duplicate keys. Iterative, so nesting costs
 * one byte of `nest` per level, never the stack. */
static int json_doc(const unsigned char *p, size_t n, const char *const keys[], struct span found[],
                    size_t nkeys, size_t *members) {
    static unsigned char nest[MAX_DEPTH]; /* the containers around s: '{' or '[' */
    const unsigned char *s = p, *end = p + n, *start = NULL;
    size_t depth = 0;
    int top = J_BAD, kind, key = -1;

    for (size_t i = 0; i < nkeys; i++) found[i].at = found[i].end = NULL, found[i].kind = J_BAD;
    *members = 0;
    s = skip_space(s, end);

parse_value:
    if (s >= end) return J_BAD;
    if (*s == '{' || *s == '[') {
        if (depth == MAX_DEPTH) return J_BAD;
        kind = *s == '{' ? J_OBJECT : J_ARRAY;
        if (depth == 0) top = kind;
        nest[depth++] = *s;
        s = skip_space(s + 1, end);
        if (s < end && *s == (nest[depth - 1] == '{' ? '}' : ']')) {
            s++;
            depth--;
            goto ended;
        }
        if (nest[depth - 1] == '{') goto parse_member;
        goto parse_value;
    }
    if (*s == '"') {
        if (!scan_string(&s, end, NULL)) return J_BAD;
        kind = J_STRING;
    } else if (literal(&s, end, "null") || literal(&s, end, "true") || literal(&s, end, "false") ||
               literal(&s, end, "NaN") || literal(&s, end, "Infinity") || literal(&s, end, "-Infinity")) {
        kind = J_OTHER;
    } else if ((kind = scan_number(&s, end)) == J_BAD) {
        return J_BAD;
    }
    if (depth == 0) top = kind;

ended: /* a value of this kind has just ended at s */
    if (depth == 0) return skip_space(s, end) == end ? top : J_BAD;
    if (depth == 1 && nest[0] == '{') {
        (*members)++;
        if (key >= 0) found[key].at = start, found[key].end = s, found[key].kind = kind;
    }
    s = skip_space(s, end);
    if (s >= end) return J_BAD;
    if (*s == ',') {
        s = skip_space(s + 1, end);
        if (nest[depth - 1] == '{') goto parse_member;
        goto parse_value;
    }
    if (*s != (nest[depth - 1] == '{' ? '}' : ']')) return J_BAD;
    s++;
    kind = nest[--depth] == '{' ? J_OBJECT : J_ARRAY;
    goto ended;

parse_member: /* a key, a colon, then its value */
    if (s >= end || *s != '"') return J_BAD;
    if (depth == 1) {
        char name[32];
        struct text t = {name, sizeof name, 0, 1};
        if (!scan_string(&s, end, &t)) return J_BAD;
        key = -1;
        for (size_t i = 0; i < nkeys && t.ascii && t.len <= t.cap; i++)
            if (strlen(keys[i]) == t.len && memcmp(keys[i], name, t.len) == 0) key = (int)i;
    } else if (!scan_string(&s, end, NULL)) {
        return J_BAD;
    }
    s = skip_space(s, end);
    if (s >= end || *s != ':') return J_BAD;
    s = skip_space(s + 1, end);
    if (depth == 1) start = s;
    goto parse_value;
}

/* A string value's decoded text into t; 0 unless v is a string. */
static int string_of(struct span v, struct text *t) {
    const unsigned char *s = v.at;
    return v.kind == J_STRING && scan_string(&s, v.end, t);
}

static int string_is(struct span v, const char *want) {
    char buf[16];
    struct text t = {buf, sizeof buf, 0, 1};
    return string_of(v, &t) && t.ascii && t.len == strlen(want) && t.len <= t.cap && memcmp(buf, want, t.len) == 0;
}

/* An integer value (never a float or a bool), saturated far beyond any port or PID. */
static int int_of(struct span v, long long *out) {
    const unsigned char *s = v.at;
    long long value = 0;
    if (v.kind != J_INT) return 0;
    int negative = *s == '-';
    for (s += negative; s < v.end; s++)
        if (value < 1000000000000LL) value = value * 10 + (*s - '0');
    *out = negative ? -value : value;
    return 1;
}

/* ---- the daemon ------------------------------------------------------------------------------- */

struct endpoint {
    struct sockaddr_in addr;
    char host[INET_ADDRSTRLEN + 1];
    long long port;
    size_t token_len;
};

static char token[MAX_HANDSHAKE];

/* forward.endpoint_of: IPv4 loopback only, a sane token, and a PID that exists (a dead daemon
 * is skipped for free). */
static int endpoint_of(const unsigned char *hs, size_t n, struct endpoint *ep) {
    static const char *const keys[] = {"host", "port", "token", "pid"};
    struct span v[COUNT(keys)];
    size_t members;
    long long pid;
    if (!utf8_valid(hs, n) || json_doc(hs, n, keys, v, COUNT(keys), &members) != J_OBJECT || members == 0)
        return 0;
    memset(ep, 0, sizeof *ep);

    /* host: absent or "localhost" means 127.0.0.1; an IPv4 address in 127/8, read as Python's
     * socket reads it first (inet_pton), never looked up */
    if (v[0].at == NULL) {
        strcpy(ep->host, "127.0.0.1");
    } else {
        struct text t = {ep->host, sizeof ep->host - 1, 0, 1};
        if (!string_of(v[0], &t) || !t.ascii || t.len > t.cap || memchr(ep->host, '\0', t.len) != NULL)
            return 0;
        ep->host[t.len] = '\0';
        if (strcmp(ep->host, "localhost") == 0) strcpy(ep->host, "127.0.0.1");
    }
    if (strncmp(ep->host, "127.", 4) != 0 || inet_pton(AF_INET, ep->host, &ep->addr.sin_addr) != 1) return 0;
    if (!int_of(v[1], &ep->port) || ep->port <= 0 || ep->port > 65535) return 0;

    /* token: a non-empty ASCII string with no CR, LF or space */
    struct text t = {token, sizeof token, 0, 1};
    if (!string_of(v[2], &t) || !t.ascii || t.len == 0 || t.len > t.cap) return 0;
    if (memchr(token, '\r', t.len) || memchr(token, '\n', t.len) || memchr(token, ' ', t.len)) return 0;
    ep->token_len = t.len;

    if (!int_of(v[3], &pid) || pid <= 0 || pid > INT_MAX || kill((pid_t)pid, 0) != 0) return 0;
    ep->addr.sin_family = AF_INET;
    ep->addr.sin_port = htons((unsigned short)ep->port);
    return 1;
}

/* Waits until fd is ready for events or the deadline passes; 1 when ready. */
static int wait_until(int fd, short events, double deadline) {
    for (;;) {
        double left = (deadline - now()) * 1000.0;
        if (left <= 0) return 0;
        int ms = (int)left;
        if ((double)ms < left) ms++;
        struct pollfd pfd = {fd, events, 0};
        int ready = poll(&pfd, 1, ms);
        if (ready > 0) return 1;
        if (ready == 0 || errno != EINTR) return 0;
    }
}

/* forward.post: one HTTP/1.1 POST, read to EOF, at most MAX_RESPONSE bytes in all. The body
 * waits at request + HEAD_CAP; the headers go just before it, so the request is one buffer and
 * leaves in one send. Returns the size of the whole response in reply, or -1. */
static ssize_t post(const struct endpoint *ep, unsigned char *request, size_t body_len, double timeout,
                    unsigned char *reply) {
    static char head[HEAD_CAP];
    size_t len = 0;
    int n = snprintf(head, sizeof head,
                     "POST /hook/codex HTTP/1.1\r\nHost: %s:%lld\r\n"
                     "Content-Type: application/json\r\nAuthorization: Bearer ",
                     ep->host, ep->port);
    if (n < 0 || (size_t)n >= sizeof head || ep->token_len >= sizeof head - (size_t)n) return -1;
    len = (size_t)n;
    memcpy(head + len, token, ep->token_len);
    len += ep->token_len;
    n = snprintf(head + len, sizeof head - len, "\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n",
                 body_len);
    if (n < 0 || (size_t)n >= sizeof head - len) return -1;
    len += (size_t)n;
    unsigned char *data = request + HEAD_CAP - len;
    memcpy(data, head, len);
    size_t total = len + body_len, sent = 0;
    ssize_t got = 0;

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    int flags = fcntl(fd, F_GETFL, 0), one = 1;
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) goto fail;
    (void)setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    if (connect(fd, (const struct sockaddr *)&ep->addr, sizeof ep->addr) != 0) {
        int err = 0;
        socklen_t err_len = sizeof err;
        if (errno != EINPROGRESS && errno != EINTR) goto fail;
        if (!wait_until(fd, POLLOUT, now() + timeout)) goto fail;
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &err_len) != 0 || err != 0) goto fail;
    }
    double deadline = now() + timeout; /* sendall: one timeout for the whole request */
    while (sent < total) {
        ssize_t w = send(fd, data + sent, total - sent, 0);
        if (w > 0) {
            sent += (size_t)w;
        } else if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
            if (!wait_until(fd, POLLOUT, deadline)) goto fail;
        } else {
            goto fail;
        }
    }
    for (;;) { /* recv: a timeout for each read */
        if (!wait_until(fd, POLLIN, now() + timeout)) goto fail;
        ssize_t r = recv(fd, reply + got, (size_t)(MAX_RESPONSE + 1 - got), 0);
        if (r == 0) break;
        if (r < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) continue;
            goto fail;
        }
        got += r;
        if (got > MAX_RESPONSE) goto fail;
    }
    close(fd);
    return got;
fail:
    close(fd);
    return -1;
}

static const unsigned char *find(const unsigned char *hay, size_t n, const char *needle, int fold) {
    size_t m = strlen(needle);
    for (size_t i = 0; m <= n && i <= n - m; i++) {
        size_t k = 0;
        while (k < m && (fold && hay[i + k] >= 'A' && hay[i + k] <= 'Z' ? hay[i + k] + 32 : hay[i + k]) ==
                            (unsigned char)needle[k])
            k++;
        if (k == m) return hay + i;
    }
    return NULL;
}

/* forward.post's reading of a response: the payload after the first blank line, provided the
 * status line's second word is exactly 200 and nothing in the headers says chunked. Its
 * length, or -1. */
static ssize_t payload_of(const unsigned char *reply, size_t n, const unsigned char **payload) {
    const unsigned char *blank = find(reply, n, "\r\n\r\n", 0);
    if (blank == NULL) return -1;
    size_t head = (size_t)(blank - reply), i = 0, word;
    const unsigned char *eol = find(reply, head, "\r\n", 0);
    size_t line = eol != NULL ? (size_t)(eol - reply) : head;
    while (i < line && byte_space(reply[i])) i++;
    while (i < line && !byte_space(reply[i])) i++;
    while (i < line && byte_space(reply[i])) i++;
    word = i;
    while (i < line && !byte_space(reply[i])) i++;
    if (i - word != 3 || memcmp(reply + word, "200", 3) != 0) return -1;
    if (find(reply, head, "transfer-encoding: chunked", 1) != NULL) return -1;
    *payload = blank + 4;
    return (ssize_t)(n - head - 4);
}

/* forward.run's verdict on a reply: printed only when it is one JSON object with a member, in
 * UTF-8, that grants nothing (forward.grants_permission: a dict hookSpecificOutput whose
 * permissionDecision is "allow", or a decision of "approve"). */
static int printable(const unsigned char *body, size_t n) {
    static const char *const keys[] = {"hookSpecificOutput", "decision"};
    static const char *const inner_keys[] = {"permissionDecision"};
    struct span v[COUNT(keys)], inner[COUNT(inner_keys)];
    size_t members;
    if (!utf8_valid(body, n) || json_doc(body, n, keys, v, COUNT(keys), &members) != J_OBJECT || members == 0)
        return 0;
    if (string_is(v[1], "approve")) return 0;
    if (v[0].kind == J_OBJECT &&
        json_doc(v[0].at, (size_t)(v[0].end - v[0].at), inner_keys, inner, COUNT(inner_keys), &members) ==
            J_OBJECT &&
        string_is(inner[0], "allow"))
        return 0;
    return 1;
}

/* forward._timeout: the value after the first --timeout when it is a number in (0, 60]. */
static double timeout_arg(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--timeout") != 0) continue;
        if (i + 1 >= argc) return DEFAULT_TIMEOUT;
        const unsigned char *s = (const unsigned char *)argv[i + 1];
        size_t n = strlen(argv[i + 1]), k, j = 0, mantissa = 0, exponent = 1;
        while (n > 0 && (k = space_at(s, n)) > 0) s += k, n -= k;
        while (n > 0 && (k = space_before(s, n)) > 0) n -= k;
        /* float()'s decimal forms only: [+-] digits [. digits] [e [+-] digits]. inf and nan
         * would fail the range check anyway, and strtod's hex forms are not Python's. */
        if (j < n && (s[j] == '+' || s[j] == '-')) j++;
        for (; j < n && s[j] >= '0' && s[j] <= '9'; j++) mantissa++;
        if (j < n && s[j] == '.')
            for (j++; j < n && s[j] >= '0' && s[j] <= '9'; j++) mantissa++;
        if (j < n && (s[j] == 'e' || s[j] == 'E')) {
            j++;
            if (j < n && (s[j] == '+' || s[j] == '-')) j++;
            for (exponent = 0; j < n && s[j] >= '0' && s[j] <= '9'; j++) exponent++;
        }
        char *end = NULL;
        double value = mantissa > 0 && exponent > 0 && j == n ? strtod((const char *)s, &end) : 0;
        return value > 0 && value <= MAX_TIMEOUT && end == (const char *)s + n ? value : DEFAULT_TIMEOUT;
    }
    return DEFAULT_TIMEOUT;
}

/* forward.run: forward one hook event. Always exits 0: Truthstone never blocks by crashing. */
int main(int argc, char **argv) {
    static unsigned char request[HEAD_CAP + MAX_STDIN + 1];
    static unsigned char handshake[MAX_HANDSHAKE + 1];
    static unsigned char reply[MAX_RESPONSE + 1];
    unsigned char *body = request + HEAD_CAP;
    const unsigned char *payload = NULL;
    struct endpoint ep;

    signal(SIGPIPE, SIG_IGN); /* a closed pipe or socket is an error to fail open on, not a death */
    if (disabled()) return 0;
    ssize_t n = read_all(STDIN_FILENO, body, MAX_STDIN + 1);
    if (n <= 0 || n > MAX_STDIN) return 0;
    ssize_t i = 0;
    while (i < n && byte_space(body[i])) i++;
    if (i == n) return 0;
    ssize_t hs = read_handshake(handshake);
    if (hs < 0 || !endpoint_of(handshake, (size_t)hs, &ep)) return 0;
    ssize_t got = post(&ep, request, (size_t)n, timeout_arg(argc, argv), reply);
    if (got < 0) return 0;
    ssize_t len = payload_of(reply, (size_t)got, &payload);
    if (len <= 0 || !printable(payload, (size_t)len)) return 0;
    write_all(STDOUT_FILENO, payload, (size_t)len);
    return 0;
}
