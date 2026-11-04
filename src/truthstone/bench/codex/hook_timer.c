/*
 * The benchmark's hook timer (golden amendment G9, target T6). Installed identically in both
 * arms: the Codex plugin's launcher runs it in place of the guard's hook runtime. It runs the
 * runtime ($HOOK_RUNNER) with the same arguments, stdin, stdout and stderr, and appends the
 * runtime's wall time, spawn to exit, to $HOOK_TRACE_DIR/guard-timing.jsonl. It writes nothing
 * else and returns the runtime's exit status, so the host sees exactly what the runtime said.
 * Its own cost (one fork and exec, well under a millisecond) is counted against the guard.
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    struct timespec start, end, wall;
    clock_gettime(CLOCK_MONOTONIC, &start);
    clock_gettime(CLOCK_REALTIME, &wall);
    const char *runner = getenv("HOOK_RUNNER");
    if (runner == NULL || runner[0] == '\0') {
        return 0;
    }
    pid_t pid = fork();
    if (pid < 0) {
        argv[0] = (char *)runner;
        execv(runner, argv);
        return 0;
    }
    if (pid == 0) {
        argv[0] = (char *)runner;
        execv(runner, argv);
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
            fprintf(out, "{\"event\": \"%s\", \"ts\": %ld.%06ld, \"ms\": %.3f, \"exit\": %d}\n",
                    argc > 1 ? argv[1] : "", (long)wall.tv_sec, (long)(wall.tv_nsec / 1000), ms,
                    WIFEXITED(status) ? WEXITSTATUS(status) : -1);
            fclose(out);
        }
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 0;
}
