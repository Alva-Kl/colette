# fake-template

A placeholder project used by the colette sandbox to exercise `cmd_create`'s
`"directory"`-type template copy path (`shutil.copytree`). It does nothing
real — the sandbox's seeded hooks (`.oncreate`/`.onstart`/`.onstop`/etc.)
only `echo`/`touch`/`sleep`, they never build or run anything.
