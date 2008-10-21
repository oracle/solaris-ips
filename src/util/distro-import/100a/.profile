#
# Simple profile places /usr/gnu/bin at front,
# adds /usr/X11/bin, /usr/sbin and /sbin to the end.
#
# Use less(1) as the default pager for the man(1) command.
#
export PATH=/usr/gnu/bin:/usr/bin:/usr/X11/bin:/usr/sbin:/sbin
export MANPATH=/usr/gnu/share/man:/usr/share/man:/usr/X11/share/man
export PAGER="/usr/bin/less -ins"

#
# Define default prompt to <username>@<hostname>:<path><"($|#) ">
# and print '#' for user "root" and '$' for normal users.
#
PS1='${LOGNAME}@$(hostname):$(
    [[ "$LOGNAME" = "root" ]] && printf "%s" "${PWD/${HOME}/~}# " ||
    printf "%s" "${PWD/${HOME}/~}\$ ")'
