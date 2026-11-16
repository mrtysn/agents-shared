# Publishing pages on the personal machine

The personal-profile half of [artifacts](../artifacts.md): the publishing tool it names.

A page meant for someone else goes out with `notes-publish FILE.html` (private until an
audience is set with `--audience`), which bundles it with `project-lifecycle page-bundle`
and serves it on the notes site behind the portal; game-venture's publish bundles the same
way. Say in one line that the page can be published that way; never publish on your own
initiative. A document for notes-shared starts from `page-new` like any other page.

Publishing from a session leaves the page private: `--audience` is refused in an agent
session, and a `!` command at the prompt runs inside it, so it is refused too. To make a page
public, give the user the `cd <folder> && notes-publish --audience public FILE` line in a code
block for a separate terminal window.
