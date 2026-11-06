/*
 * The benchmark's hook timer (golden amendments G9 and G24, target T6). Installed identically
 * in both arms: the Codex plugin's launcher runs it in place of the guard's hook runtime.
 *
 * It runs what the launcher's own hot path would run. For the events that only forward, that
 * is the native forwarder $PLUGIN_DATA/lean/forward-native, once SessionStart has built it
 * (G24: the timer starts it itself, as the launcher does, so no shell sits between the two).
 * Otherwise, and for every other event, it runs $HOOK_RUNNER: the lean Python forwarder or
 * the runtime. Either one gets the same arguments, stdin, stdout and stderr.
 *
 * It appends the child's wall time, spawn to exit, and the route it took, to
 * $HOOK_TRACE_DIR/guard-timing.jsonl. It writes nothing else. It returns what the launcher
 * would: 0 after the native forwarder, otherwise the runner's exit status. Its own cost (one
 * fork and exec, well under a millisecond) is counted against the guard.
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static const char *const HOT[] = {"pre-tool-use", "post-tool-use", "stop", "subagent-stop", "session-end"};

/* The launcher's test: a hot event, $PLUGIN_DATA set, and forward-native a regular file the
 * user may execute (`[ -f ] && [ -x ]`). Fills path and returns 1 when the forwarder runs. */
static int native_forwarder(const char *event, char *path, size_t size) {
    int hot = 0;
    for (size_t i = 0; i < sizeof HOT / sizeof HOT[0]; i++) {
        if (strcmp(event, HOT[i]) == 0) {
            hot = 1;
        }
    }
    const char *data = getenv("PLUGIN_DATA");
    if (!hot || data == NULL || data[0] == '\0') {
        return 0;
    }
    int n = snprintf(path, size, "%s/lean/forward-native", data);
    struct stat st;
    return n > 0 && (size_t)n < size && stat(path, &st) == 0 && S_ISREG(st.st_mode) && access(path, X_OK) == 0;
}

/* Replaces this process with the forwarder (the launcher's --timeout budget: 2 s for
 * session-end, else 4 s) or with the runner; returns only when neither could start. */
static void run(int native, char *forwarder, const char *event, const char *runner, char **argv) {
    if (native) {
        char flag[] = "--timeout";
        char budget[] = "4";
        if (strcmp(event, "session-end") == 0) {
            budget[0] = '2';
        }
        char *args[] = {forwarder, flag, budget, NULL};
        execv(forwarder, args);
    }
    argv[0] = (char *)runner;
    execv(runner, argv);
}

int main(int argc, char **argv) {
    struct timespec start, end, wall;
    clock_gettime(CLOCK_MONOTONIC, &start);
    clock_gettime(CLOCK_REALTIME, &wall);
    const char *runner = getenv("HOOK_RUNNER");
    if (runner == NULL || runner[0] == '\0') {
        return 0;
    }
    const char *event = argc > 1 ? argv[1] : "";
    char forwarder[4096];
    int native = native_forwarder(event, forwarder, sizeof forwarder);
    pid_t pid = fork();
    if (pid < 0) {
        run(native, forwarder, event, runner, argv);
        return 0;
    }
    if (pid == 0) {
        run(native, forwarder, event, runner, argv);
        _exit(127);
    }
    int status = 0;
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {
    }
    clock_gettime(CLOCK_MONOTONIC, &end);
    double ms = (double)(end.tv_sec - start.tv_sec) * 1e3 + (double)(end.tv_nsec - start.tv_nsec) / 1e6;
    const char *dir = getenv("HOOK_TRACE_DIR");
    if (dir != NULL && dir[0] != '\0') {
        char path[4096];
        snprintf(path, sizeof path, "%s/guard-timing.jsonl", dir);
        FILE *out = fopen(path, "a");
        if (out != NULL) {
            fprintf(out, "{\"event\": \"%s\", \"ts\": %ld.%06ld, \"ms\": %.3f, \"exit\": %d, \"route\": \"%s\"}\n",
                    event, (long)wall.tv_sec, (long)(wall.tv_nsec / 1000), ms,
                    WIFEXITED(status) ? WEXITSTATUS(status) : -1, native ? "native" : "runner");
            fclose(out);
        }
    }
    if (native) {
        return 0; /* the launcher runs the forwarder, never execs it: its own exit 0 stands */
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 0;
}
