/*
 * Copyright (c) 2010, 2017, Oracle and/or its affiliates. All rights reserved.
 */

#include <door.h>
#include <errno.h>
#include <fcntl.h>
#include <libscf.h>
#include <netdb.h>
#include <poll.h>
#include <priv.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <thread.h>
#include <unistd.h>
#include <zone.h>
#include <zoneproxy_impl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/stropts.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>

#define	EXIT_DAEMON_TERM	3
#define	SLEEP_INTERVAL		15
#define	SLEEP_DURATION		180

static int g_pipe_fd;

static int zp_unregister_zone(void);

/* ARGSUSED */
static void
s_handler(void)
{
	int sig;
	int do_exit = 0;
	sigset_t wait_sigs;

	(void) sigfillset(&wait_sigs);

	while (do_exit == 0) {
		if (sigwait(&wait_sigs, &sig) != 0)
			continue;

		if (sig == SIGINT || sig == SIGTERM || sig == SIGHUP)
			do_exit++;
	}

	(void) zp_unregister_zone();

	exit(EXIT_SUCCESS);
}

static void
usage(void)
{
	(void) printf("usage: zoneproxy-client -s proxyaddr:proxyport\n");
	exit(EXIT_FAILURE);
}

static void
close_door_descs(door_desc_t *dp, uint_t ndesc)
{
	int fd;

	while (ndesc > 0) {
		fd = dp->d_data.d_desc.d_descriptor;
		if (dp->d_attributes & DOOR_DESCRIPTOR)
			(void) close(fd);
		dp++;
		ndesc--;
	}
}

static void
zp_perror(int res)
{
	if (res == ZP_STATUS_PERMISSION) {
		(void) fprintf(stderr, "Insufficient privileges for zoneproxyd"
		    " access\n");
	} else if (res == ZP_STATUS_INVALID) {
		(void) fprintf(stderr,
		    "Invalid argument provided to zoneproxyd\n");
	} else if (res == ZP_STATUS_ERROR) {
		(void) fprintf(stderr,
		    "Zoneproxyd encountered an internal error\n");
	} else if (res == ZP_STATUS_UNKNOWN) {
		(void) fprintf(stderr, "The zoneproxyd did not recognize the"
		    " command\n");
	} else if (res != ZP_STATUS_OK) {
		(void) fprintf(stderr,
		    "The daemon returned an unrecognized response");
	}
}

static int
zp_ping_proxy(void)
{
	int doorfd;
	int *res;
	int cmd[2];
	door_arg_t dparam;

	if ((doorfd = open(ZP_DOOR_PATH, O_RDONLY)) < 0) {
		if (errno == ENOENT) {
			return (-2);
		} else {
			perror("open");
			return (-1);
		}
	}


	cmd[0] = ZP_CMD_PING;

	dparam.data_ptr = (char *)cmd;
	dparam.data_size = sizeof (cmd);
	dparam.desc_ptr = (door_desc_t *)NULL;
	dparam.desc_num = 0;
	dparam.rbuf = NULL;
	dparam.rsize = 0;

	if (door_call(doorfd, &dparam) < 0) {
		if (errno == EBADF) {
			(void) close(doorfd);
			return (-2);
		} else {
			perror("door_call");
			(void) close(doorfd);
			return (-1);
		}
	}

	(void) close(doorfd);
	/* LINTED */
	res = (int *)dparam.data_ptr;

	if (res[1] != ZP_STATUS_OK) {
		zp_perror(res[1]);
		return (-1);
	}

	return (0);
}


static int
zp_unregister_zone(void)
{
	int doorfd;
	int *res;
	int cmd[2];
	door_arg_t dparam;
	zoneid_t zid;

	if ((doorfd = open(ZP_DOOR_PATH, O_RDONLY)) < 0) {
		perror("open");
		return (-1);
	}

	zid = getzoneid();

	cmd[0] = ZP_CMD_REMOVE_LISTENER;
	cmd[1] = zid;

	dparam.data_ptr = (char *)cmd;
	dparam.data_size = sizeof (cmd);
	dparam.desc_ptr = (door_desc_t *)NULL;
	dparam.desc_num = 0;
	dparam.rbuf = NULL;
	dparam.rsize = 0;

	if (door_call(doorfd, &dparam) < 0) {
		perror("door_call");
		(void) close(doorfd);
		return (-1);
	}

	(void) close(doorfd);
	/* LINTED */
	res = (int *)dparam.data_ptr;

	if (res[1] != ZP_STATUS_OK) {
		zp_perror(res[1]);
		return (-1);
	}

	return (0);
}

static int
zp_register_socket(int sock, int *fdp)
{
	int doorfd;
	int *res;
	int cmd[2];
	door_arg_t dparam;
	door_desc_t doord;
	zoneid_t zid;

	if ((doorfd = open(ZP_DOOR_PATH, O_RDONLY)) < 0) {
		perror("open");
		return (-1);
	}

	zid = getzoneid();

	cmd[0] = ZP_CMD_NEW_LISTENER;
	cmd[1] = zid;

	doord.d_attributes = DOOR_DESCRIPTOR;
	doord.d_data.d_desc.d_descriptor = sock;

	dparam.data_ptr = (char *)cmd;
	dparam.data_size = sizeof (cmd);
	dparam.desc_ptr = (door_desc_t *)&doord;
	dparam.desc_num = 1;
	dparam.rbuf = NULL;
	dparam.rsize = 0;

	if (door_call(doorfd, &dparam) < 0) {
		perror("door_call");
		(void) close(doorfd);
		return (-1);
	}

	(void) close(doorfd);
	/* LINTED */
	res = (int *)dparam.data_ptr;

	if (res[1] != ZP_STATUS_OK) {
		zp_perror(res[1]);
		return (-1);
	}

	/* Caller should have passed us a pipe fd */
	if (dparam.desc_num > 1) {
		close_door_descs(dparam.desc_ptr + 1, dparam.desc_num - 1);
	}

	if (dparam.desc_num > 0) {
		if (fdp) {
			*fdp = dparam.desc_ptr->d_data.d_desc.d_descriptor;
		} else {
			(void) close(
			    dparam.desc_ptr->d_data.d_desc.d_descriptor);
		}
	} else {
		(void) fprintf(stderr, "Daemon didn't return pipefd\n");
		return (-1);
	}

	return (0);
}

static void
daemonize_ready(char status)
{
	/*
	 * wake the parent with a clue
	 */
	(void) write(g_pipe_fd, &status, 1);
	(void) close(g_pipe_fd);
}

static int
daemonize_start(void)
{
	char data;
	int status;

	int filedes[2];
	pid_t pid;

	(void) close(0);
	(void) dup2(2, 1);

	if (pipe(filedes) < 0)
		return (-1);

	(void) fflush(NULL);

	if ((pid = fork1()) < 0)
		return (-1);

	if (pid != 0) {
		/*
		 * parent
		 */
		(void) close(filedes[1]);
		if (read(filedes[0], &data, 1) == 1) {
			/* forward ready code via exit status */
			exit(data);
		}
		status = -1;
		(void) wait4(pid, &status, 0, NULL);
		/* daemon process exited before becoming ready */
		if (WIFEXITED(status)) {
			/* assume daemon process printed useful message */
			exit(WEXITSTATUS(status));
		} else {
			(void) fprintf(stderr,
			    "daemon process killed or died\n");
			exit(EXIT_FAILURE);
		}
	}

	/*
	 * child
	 */
	g_pipe_fd = filedes[1];
	(void) close(filedes[0]);

	/*
	 * generic Unix setup
	 */
	(void) setsid();
	(void) umask(0000);

	return (0);
}

void
drop_privs(void)
{
	priv_set_t *pPrivSet = NULL;
	priv_set_t *lPrivSet = NULL;

	if ((pPrivSet = priv_str_to_set("basic", ",", NULL)) == NULL) {
		(void) fprintf(stderr, "Unable to get 'basic' privset\n");
		exit(EXIT_FAILURE);
	}

	/* Drop any privs out of the basic set that we won't need */
	(void) priv_delset(pPrivSet, PRIV_FILE_LINK_ANY);
	(void) priv_delset(pPrivSet, PRIV_PROC_INFO);
	(void) priv_delset(pPrivSet, PRIV_PROC_SESSION);
	(void) priv_delset(pPrivSet, PRIV_PROC_FORK);
	(void) priv_delset(pPrivSet, PRIV_PROC_EXEC);
	(void) priv_delset(pPrivSet, PRIV_FILE_WRITE);
	/* We need access to ZP_DOOR_PATH after dropping the privileges. */
	(void) priv_addset(pPrivSet, PRIV_FILE_DAC_READ);

	/* Set permitted set */
	if (setppriv(PRIV_SET, PRIV_PERMITTED, pPrivSet) != 0) {
		(void) fprintf(stderr, "Unable to drop privs\n");
		exit(EXIT_FAILURE);
	}

	/* clear limit set */
	if ((lPrivSet = priv_allocset()) == NULL) {
		(void) fprintf(stderr, "Unable to allocate privset\n");
		exit(EXIT_FAILURE);
	}

	priv_emptyset(lPrivSet);

	if (setppriv(PRIV_SET, PRIV_LIMIT, lPrivSet) != 0) {
		(void) fprintf(stderr, "Unable to set limit set\n");
		exit(EXIT_FAILURE);
	}

	priv_freeset(lPrivSet);
	priv_freeset(pPrivSet);
}

int
main(int argc, char **argv)
{
	extern char *optarg;
	char *proxystr = NULL;
	char *proxyhost, *proxyport;
	int rc, err_code;
	int sval;
	int sockfd;
	int pipefd = -1;
	int sleeptime = 0;
	boolean_t quit = B_FALSE;
	struct addrinfo hints;
	struct addrinfo *ai = NULL;
	sigset_t main_ss;

	while ((rc = getopt(argc, argv, "s:")) != -1) {
		switch (rc) {
		case 's':
			proxystr = optarg;
			break;
		case ':':
			(void) fprintf(stderr, "Option -%c requires operand\n",
			    optopt);
			usage();
			break;
		case '?':
			(void) fprintf(stderr, "Unrecognized option -%c\n",
			    optopt);
			usage();
			break;
		default:
			break;
		}
	}

	if (proxystr == NULL) {
		usage();
	}

	proxyhost = strtok(proxystr, ":");
	if (proxyhost == NULL) {
		(void) fprintf(stderr,
		    "host must be of format hostname:port\n");
		usage();
	}
	proxyport = strtok(NULL, ":");
	if (proxyport == NULL) {
		(void) fprintf(stderr,
		    "host must be of format hostname:port\n");
		usage();
	}

	(void) signal(SIGPIPE, SIG_IGN);

	if (daemonize_start() < 0) {
		(void) fprintf(stderr, "Unable to start daemon\n");
		exit(EXIT_FAILURE);
	}

	/*
	 * Before doing anything else, check to see if it's possible to reach
	 * the proxyd.  If not, sit in a loop waiting for a period of time.
	 * If the proxyd doesn't come on-line after waiting, return an error
	 * code that tells smf to enter this service into maintenance mode.
	 */
	while ((rc = zp_ping_proxy()) < -1) {
		(void) sleep(SLEEP_INTERVAL);
		sleeptime += SLEEP_INTERVAL;
		if (sleeptime >= SLEEP_DURATION)
			break;
	}

	if (rc == -2) {
		/* never successfully reached proxy */
		(void) fprintf(stderr, "Timed out trying to reach proxy\n");
		exit(SMF_EXIT_ERR_FATAL);
	} else if (rc == -1) {
		/* got some other error */
		exit(EXIT_FAILURE);
	}

	(void) memset(&hints, 0, sizeof (struct addrinfo));
	hints.ai_flags = AI_ALL;
	hints.ai_family = PF_UNSPEC;
	hints.ai_socktype = SOCK_STREAM;

	if ((err_code = getaddrinfo(proxyhost, proxyport, &hints, &ai))
	    != 0) {
		(void) fprintf(stderr, "Unable to perform name lookup\n");
		(void) fprintf(stderr, "%s: %s\n", proxyhost,
		    gai_strerror(err_code));
		exit(EXIT_FAILURE);
	}

	if ((sockfd = socket(ai->ai_family, SOCK_STREAM, 0)) < 0) {
		perror("socket");
		exit(EXIT_FAILURE);
	}

	sval = 1;
	if (setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, (char *)&sval,
	    sizeof (sval)) < 0) {
		perror("setsocketopt");
		exit(EXIT_FAILURE);
	}

	if (bind(sockfd, (struct sockaddr *)ai->ai_addr, ai->ai_addrlen) < 0) {
		if (errno != EADDRINUSE) {
			perror("bind");
			exit(EXIT_FAILURE);
		}
		/*
		 * If the socket is in use, call zoneproxyd and
		 * ask it to un-register the current socket.  Then
		 * try again.
		 */

		if (zp_unregister_zone() < 0) {
			exit(EXIT_FAILURE);
		}

		if (bind(sockfd, (struct sockaddr *)ai->ai_addr,
		    ai->ai_addrlen) < 0) {
			perror("bind");
			exit(EXIT_FAILURE);
		}

	}

	if (listen(sockfd, 5) < 0) {
		perror("listen");
		exit(EXIT_FAILURE);
	}

	if (zp_register_socket(sockfd, &pipefd) < 0) {
		exit(EXIT_FAILURE);
	}

	/*
	 * At this point, the proxyd has a copy of the socket and will answer
	 * all incoming connection requests.  Close our reference to the socket
	 * here.
	 */
	(void) close(sockfd);
	freeaddrinfo(ai);

	daemonize_ready(0);

	(void) sigfillset(&main_ss);

	if (thr_sigsetmask(SIG_BLOCK, &main_ss, NULL) < 0) {
		perror("thr_sigsetmask");
		exit(EXIT_FAILURE);
	}

	/* create signal handling thread */
	if (thr_create(NULL, 0, (void *(*)(void *))s_handler, NULL,
	    THR_BOUND, NULL) < 0) {
		perror("thr_create");
		exit(EXIT_FAILURE);
	}

	drop_privs();

	/* Wait for signal to quit */
	while (quit == B_FALSE) {
		struct pollfd pfd[1];
		boolean_t unexpected = B_FALSE;
		char value;

		/*
		 * Pipe to proxyd notfies client when to quit.  If the proxy
		 * writes a byte to the pipe, or the pipe is closed
		 * unexpectedly, POLLIN will be true, telling us to exit.
		 */
		pfd[0].fd = pipefd;
		pfd[0].events = POLLIN;

		if (poll(pfd, 1, INFTIM) < 0) {
			if (errno == EINTR) {
				continue;
			}
			perror("poll");
			exit(EXIT_FAILURE);
		}

		if (pfd[0].revents & POLLIN) {
			rc = read(pipefd, &value, 1);
			if (rc < 0) {
				perror("read");
				exit(EXIT_FAILURE);
			}
			quit = B_TRUE;
			if (rc == 0)
				unexpected = B_TRUE;
		} else if (pfd[0].revents & (POLLERR | POLLHUP | POLLNVAL)) {
			quit = B_TRUE;
			unexpected = B_TRUE;
		}

		if (quit && unexpected) {
			exit(EXIT_DAEMON_TERM);
		}

	}

	return (0);
}
