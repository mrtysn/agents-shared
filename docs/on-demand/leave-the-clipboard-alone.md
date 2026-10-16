# Leave the clipboard alone

**Never write to the user's clipboard: no `pbcopy`, no `osascript … set the clipboard`, no
`xclip`, `xsel` or `wl-copy`, and no tool that does it for you.** The clipboard holds whatever the
user copied last, and nothing keeps a copy: a write destroys it for good.

Text the user should paste goes in the reply when it is short (a console snippet, a command), and in
a file whose absolute path you give when it is long. If the user asks for something to be put on the
clipboard, that request is the permission; nothing else is.

Reading the clipboard (`pbpaste`) is not covered here and needs its own reason.

## Provenance

Oct 15 2026, link-keeper: to debug a browser extension in the page console, a session ran `pbcopy`
on a 27 KB script without asking, replacing what the user had copied. The user: "dont we have rule
against messing with my clipboard? type it in the chat, dont touch it again." There was no such rule;
this is it.
