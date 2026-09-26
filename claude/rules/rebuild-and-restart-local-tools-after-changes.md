# Rebuild and restart local tools after changes

**A change to a tool the user runs is not finished until the running copy has it.**
Committed source that the installed app never saw is a bug report waiting to happen:
the user opens the old build, sees nothing changed or something broken, and has to
ask. Run the repo's own build, bundle, or install step yourself — never hand it to
the user.

## What to do

1. **Test first.** Run the repo's tests or its self-check before building. Never
   tell the user to relaunch something that has not been shown to start.
2. **Rebuild and install** through the repo's own entry point (`bundle.sh`,
   `install.sh`, `./<tool>.zsh --install`, `make install` — whatever its
   `CLAUDE.md` or README names). Not a hand-made copy, link, or `launchctl` call.
3. **Get the new build running, judged by what the tool is:**
   - **Background agent, daemon, or menu bar app with no window** — restart it
     through the repo's install path. It takes no focus.
   - **A windowed app the user is actively iterating on in this session** —
     restart it, launching through `quiet-open` per [window focus](window-focus.md).
   - **A windowed app the user is not iterating on, or one `quiet-open` cannot
     launch** — leave it running and say once: "rebuilt; quit and reopen X".
4. **Check that exactly one copy is running, and it is the new one.** An instance
   opened by hand outside the launch agent survives a reinstall and keeps the old
   build alive beside the new one.

## Where a repo says otherwise

A repo's `CLAUDE.md` or memory that reserves restarting to the user — a proxy other
sessions depend on, an app whose permissions a relaunch would revoke — wins over
step 3. Rebuild anyway, then say a restart is needed.

## Provenance

Sep 2026, the same correction in five repos inside a week: "did you rebuild it?
close the app. rebuild it. relaunch it", "claude you are to run bundle, not me!
after you make changes, you rebuild.", "please rebuild without having me to
prompt", "why are you not testing before telling me to relaunch. it failed
again.", and a memory-guard change committed and pushed while the old build kept
running. The first three had been saved only as that repo's memory.
