/*
 * CDDL HEADER START
 *
 * The contents of this file are subject to the terms of the
 * Common Development and Distribution License (the "License").
 * You may not use this file except in compliance with the License.
 *
 * You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
 * or http://www.opensolaris.org/os/licensing.
 * See the License for the specific language governing permissions
 * and limitations under the License.
 *
 * When distributing Covered Code, include this CDDL HEADER in each
 * file and include the License file at usr/src/OPENSOLARIS.LICENSE.
 * If applicable, add the following below this CDDL HEADER, with the
 * fields enclosed by brackets "[]" replaced with your own identifying
 * information: Portions Copyright [yyyy] [name of copyright owner]
 *
 * CDDL HEADER END
 */
/*
 * Copyright (c) 2010, 2012, Oracle and/or its affiliates. All rights reserved.
 */

/*
 * The zone proxy daemon and zone proxy client.
 *
 * For package operations in zones, the system must make available a certain
 * group of publishers and repositories to client zones.  This ensures that data
 * necessary for installing or updating a zone is always available to zones
 * consumers, regardless of the exact network configuration within the local
 * zone.  In order to accomplish this, the proxy daemon and proxy client provide
 * a TCP proxy to a special repository that is maintained in the global zone.
 *
 * The zone-proxy client is responsible for creating a listening TCP socket in a
 * pre-determined location, and then passing control of that socket to the proxy
 * daemon.  Once the proxy client has completed this hand-off, it sleeps in the
 * local zone, waiting for notification of any changes in the global zone.  If
 * the proxy daemon exits, or is re-configured, the proxy client creates a new
 * socket, and the process is repeated.
 *
 * The proxy daemon listens on the sockets passed to it by the proxy client, and
 * when it gets a new connection, establishes a connection to the zones
 * repository that serves packaging information.  The proxy daemon and client
 * pass information through a door.  The daemon also listens for notifications
 * about zone startup and shutdown on the door.  (zoneadmd, knows to poke the
 * daemon when zones are created or destroyed).  When a zone is created, the
 * proxy daemon enters the zone, and creates a new door there, so that the
 * client and daemon can rendezvous.  The proxy daemon manages a pool of thread
 * workers for handling network connections, and has some door callbacks to
 * manage a pool of IPC threads.
 *
 * Each new connection generates a pair of sockets.  The data transfer algorithm
 * here is lockless, and depends upon event ports as the polling mechanism.  The
 * socket is dup'd, and one is always used for reading, and the other always
 * used for writing.  As long as no thread reads and writes the same fd,
 * operation is atomic, and correct.  When a thread needs data, the event
 * mechanism is used either to wait for data, or to wait to write data.
 * Although each proxy connection has a buffer, we try our best to drain that
 * buffer ASAP, especially before getting more data.
 */
#include <alloca.h>
#include <atomic.h>
#include <door.h>
#include <errno.h>
#include <fcntl.h>
#include <libcontract.h>
#include <libscf.h>
#include <limits.h>
#include <netdb.h>
#include <port.h>
#include <priv.h>
#include <pthread.h>
#include <synch.h>
#include <signal.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stropts.h>
#include <thread.h>
#include <ucred.h>
#include <unistd.h>
#include <zone.h>
#include <zoneproxy_impl.h>
#include <sys/ctfs.h>
#include <sys/contract/process.h>
#include <sys/queue.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/wait.h>

#define	PROXY_THREAD_DEFAULT		8
#define	PROXY_THREAD_MAX		20
#define	DOOR_THREAD_MAX			5
#define	DEFAULT_LOCK_ALIGN		64
#define	DEFAULT_TIMEOUT			30
#define	TIMEOUT_COUNT			4
#define	MAX_FDS_DEFAULT			6000

#define	SYSREPO_FMRI	"svc:/application/pkg/system-repository:default"
#define	SYSREPO_PG	"config"
#define	SYSREPO_HOST	"host"
#define	SYSREPO_PORT	"port"
#define	DEFAULT_HOST	"127.0.0.1"
#define	DEFAULT_PORT	"1008"

#define	BUFFER_SIZ		8168
#define	CONF_STR_SZ		2048

typedef enum {
	PROXY_USER_GENERIC = 0,
	PROXY_USER_LISTENER,
	PROXY_USER_PAIR,
	PROXY_USER_END
} pu_type_t;

typedef enum {
	PROXY_STATE_INIT = 0,
	PROXY_STATE_WAIT_CONNECT,
	PROXY_STATE_WAIT_DATA,
	PROXY_STATE_CLOSING,
	PROXY_STATE_FREED,
	PROXY_STATE_END
} proxy_state_t;

/* structure definitions */

struct proxy_user {
	pu_type_t	pu_type;
	void		(*pu_callback)(struct proxy_user *, port_event_t *);
};

struct proxy_listener {
	pu_type_t	pl_type;
	void		(*pl_callback)(struct proxy_listener *, port_event_t *);
	TAILQ_ENTRY(proxy_listener) pl_list_link;
	zoneid_t	pl_zid;
	int		pl_fd;
	mutex_t		pl_lock;
	boolean_t	pl_cleanup;
	int		pl_pipefd;
	int		pl_closefd;
	char		*pl_proxy_host;
	char		*pl_proxy_port;
	uint64_t	pl_gen;
};

struct proxy_pair {
	pu_type_t	pp_type;
	void		(*pp_callback)(struct proxy_pair *, port_event_t *);
	int		pp_readfd;
	int		pp_writefd;
	size_t		pp_fbcnt;
	proxy_state_t	pp_state;
	char		pp_buffer[BUFFER_SIZ];
};

struct proxy_config {
	mutex_t			pc_lock;
	scf_handle_t		*pc_hdl;
	scf_instance_t		*pc_inst;
	scf_propertygroup_t	*pc_pg;
	scf_property_t		*pc_prop;
	scf_value_t		*pc_val;
	char			*pc_proxy_host;
	char			*pc_proxy_port;
	uint64_t		pc_gen;
};

/* global variables */
int		g_port;
int		g_door = -1;
int		g_pipe_fd;
int		g_max_door_thread = DOOR_THREAD_MAX;
int		g_door_thread_count = 0;
uint_t		g_proxy_pair_count = 0;
thread_key_t	g_thr_info_key;
mutex_t		*g_door_thr_lock;
cond_t		*g_door_thr_cv;
mutex_t		*g_listener_lock;
mutex_t		*g_thr_pool_lock;

/* global variables protected by g_thr_pool_lock */
int		g_tp_running_threads;
int		g_tp_exited_threads;
int		g_tp_max_threads = PROXY_THREAD_MAX;
int		g_tp_min_threads = PROXY_THREAD_DEFAULT;
cond_t		g_thr_pool_cv = DEFAULTCV;

/* global variables shared between main thread and s_handler thread */
mutex_t		g_quit_lock = DEFAULTMUTEX;
cond_t		g_quit_cv = DEFAULTCV;

/* proxy config protected by internal lock */
struct proxy_config	*g_proxy_config;
boolean_t		g_config_smf;

TAILQ_HEAD(zq_queuehead, proxy_listener);
struct zq_queuehead	zone_listener_list;
static volatile boolean_t g_quit;

/* function declarations */
static struct proxy_listener *alloc_proxy_listener(void);
static struct proxy_pair *alloc_proxy_pair(void);
static int check_connect(struct proxy_pair *);
static int clone_and_register(struct proxy_pair *);
static void close_door_descs(door_desc_t *, uint_t);
static int close_on_exec(int);
static struct proxy_config *config_alloc(void);
static void config_free(struct proxy_config *);
static int config_read(struct proxy_config *);
static int contract_abandon_id(ctid_t);
static int contract_latest(ctid_t *);
static int contract_open(ctid_t, const char *, const char *, int);
static void daemonize_ready(char);
static int daemonize_start(void);
static int do_fattach(int, char *, boolean_t);
static void drop_privs(void);
static void escalate_privs(void);
static void fattach_all_zones(boolean_t);
static void free_proxy_listener(struct proxy_listener *);
static void free_proxy_pair(struct proxy_pair *);
static int init_template(void);
static void listen_func(struct proxy_listener *, port_event_t *);
static void proxy_func(struct proxy_pair *, port_event_t *);
static void *proxy_thread_loop(void *);
static void s_handler(void);
static int send_recv_data(struct proxy_pair *);
static void shutdown_proxypair(struct proxy_pair *);
static void thread_exiting(void *);
static void *thread_manager(void *);
static void usage(void);
static int zpd_add_listener(zoneid_t, int, int, int);
static void zpd_door_create_thread(door_info_t *);
static void *zpd_door_loop(void *);
static void zpd_door_server(void *, char *, size_t, door_desc_t *, uint_t);
static void zpd_fattach_zone(zoneid_t, int, boolean_t);
static struct proxy_listener *zpd_find_listener(zoneid_t);
static void zpd_listener_cleanup(struct proxy_listener *);
static int zpd_perm_check(int, zoneid_t);
static void zpd_remove_listener(struct proxy_listener *);
static int zpd_remove_zone(zoneid_t);

static void
usage(void)
{
	(void) fprintf(stderr, "Usage: zoneproxyd [-s host:port]\n");
	exit(EXIT_FAILURE);
}

static int
set_noblocking(int fd)
{
	int		flags;

	if ((flags = fcntl(fd, F_GETFL, 0)) < 0) {
		perror("fcntl (GETFL)");
		return (-1);
	}

	if (fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
		perror("fcntl (SETFL)");
		return (-1);
	}

	return (0);
}

static struct proxy_listener *
alloc_proxy_listener(void)
{
	struct proxy_listener	*listener;

	listener = malloc(sizeof (struct proxy_listener));
	if (listener == NULL) {
		perror("malloc");
		return (NULL);
	}
	(void) memset(listener, 0, sizeof (struct proxy_listener));
	listener->pl_type = PROXY_USER_LISTENER;
	listener->pl_callback = listen_func;
	listener->pl_fd = -1;
	listener->pl_pipefd = -1;
	listener->pl_closefd = -1;
	listener->pl_cleanup = B_FALSE;
	if (mutex_init(&listener->pl_lock, USYNC_THREAD, NULL) < 0) {
		perror("mutex_init");
		return (NULL);
	}

	return (listener);
}


static struct proxy_pair *
alloc_proxy_pair(void)
{
	struct proxy_pair	*pair;

	pair = malloc(sizeof (struct proxy_pair));
	if (pair == NULL) {
		perror("malloc");
		return (NULL);
	}
	(void) memset(pair, 0, sizeof (struct proxy_pair));
	pair->pp_type = PROXY_USER_PAIR;
	pair->pp_callback = proxy_func;
	pair->pp_readfd = -1;
	pair->pp_writefd = -1;

	return (pair);
}

static void
free_proxy_listener(struct proxy_listener *listener)
{
	if (listener->pl_fd > -1) {
		if (close(listener->pl_fd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
	}
	if (listener->pl_pipefd > -1) {
		if (close(listener->pl_pipefd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
	}
	if (listener->pl_closefd > -1) {
		if (close(listener->pl_closefd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
	}
	(void) mutex_destroy(&listener->pl_lock);
	free(listener->pl_proxy_host);
	free(listener->pl_proxy_port);
	free(listener);
}

static void
free_proxy_pair(struct proxy_pair *pair)
{
	if (pair->pp_readfd > -1) {
		if (close(pair->pp_readfd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
	}
	if (pair->pp_writefd > -1) {
		if (close(pair->pp_writefd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
	}
	pair->pp_state = PROXY_STATE_FREED;
	free(pair);
}

/*
 * Once a pair has been connected, dup the file descriptors, switching read and
 * write, so that both pair can be seperately queued for events.
 */
static int
clone_and_register(struct proxy_pair *pair)
{
	struct proxy_pair	*op_pair;
	int			fd;

	/* Allocate another proxy_pair object */
	op_pair = alloc_proxy_pair();
	if (op_pair == NULL) {
		return (-1);
	}

	/* Copy state */
	op_pair->pp_state = pair->pp_state;

	/* Dup fd's switching read for write */
	if ((fd = dup(pair->pp_readfd)) < 0) {
		perror("dup");
		free_proxy_pair(op_pair);
		return (-1);
	}

	op_pair->pp_writefd = fd;

	if ((fd = dup(pair->pp_writefd)) < 0) {
		perror("dup");
		free_proxy_pair(op_pair);
		return (-1);
	}

	op_pair->pp_readfd = fd;

	/* Register each pair to wait for input */
	if (port_associate(g_port, PORT_SOURCE_FD, op_pair->pp_readfd,
	    POLLIN, op_pair) < 0) {
		perror("port_associate");
		free_proxy_pair(op_pair);
		return (-1);
	}

	if (port_associate(g_port, PORT_SOURCE_FD, pair->pp_readfd,
	    POLLIN, pair) < 0) {
		perror("port_associate");
		return (-1);
	}

	/*
	 * Increment the proxy count by two, since there are two proxy-pair
	 * objects per connection, each representing one direction of the flow.
	 * The objects are shutdown separately, so each will decrment the
	 * count by one in its shutdown method.
	 */
	atomic_add_int(&g_proxy_pair_count, 2);
	/*
	 * Try to poke the thread manager.  If someone else is poking him, or
	 * he's already running, just return.  In the worst case the manager
	 * will double-check the number of threads after the timeout.
	 */
	if (mutex_trylock(g_thr_pool_lock) == 0) {
		(void) cond_signal(&g_thr_pool_cv);
		(void) mutex_unlock(g_thr_pool_lock);
	}

	return (0);
}

static void
shutdown_proxypair(struct proxy_pair *pair)
{
	(void) port_dissociate(g_port, PORT_SOURCE_FD, pair->pp_readfd);
	(void) port_dissociate(g_port, PORT_SOURCE_FD, pair->pp_writefd);

	if (pair->pp_fbcnt > 0)
		(void) write(pair->pp_writefd, pair->pp_buffer, pair->pp_fbcnt);

	(void) shutdown(pair->pp_readfd, SHUT_RD);
	(void) shutdown(pair->pp_writefd, SHUT_WR);
	free_proxy_pair(pair);
	atomic_dec_uint(&g_proxy_pair_count);
}

static int
send_recv_data(struct proxy_pair *pair)
{
	int	b_wr;
	int	b_rd;
	int	read_needed = 0;
	int	write_needed = 0;

	if (pair->pp_fbcnt == 0) /* need to read */ {
		b_rd = read(pair->pp_readfd, pair->pp_buffer, BUFFER_SIZ);
		if (b_rd < 0 && (errno == EAGAIN || errno == EWOULDBLOCK ||
		    errno == EINTR)) {
			b_rd = 0;
			read_needed = 1;
		} else if (b_rd <= 0) {
			return (-1);
		}
		pair->pp_fbcnt = b_rd;
	}

	if (pair->pp_fbcnt > 0) {
		b_wr = write(pair->pp_writefd, pair->pp_buffer, pair->pp_fbcnt);

		if (b_wr < 0) {
			if (errno != EAGAIN && errno != EWOULDBLOCK) {
				return (-1);
			}
			b_wr = 0;
		}

		if (b_wr < pair->pp_fbcnt) {
			if (b_wr != 0) {
				(void) memmove(pair->pp_buffer,
				    pair->pp_buffer + b_wr,
				    pair->pp_fbcnt - b_wr);
				pair->pp_fbcnt -= b_wr;
			}
			write_needed = 1;
			/* If the write side is slow, disable read here */
			read_needed = 0;
		} else {
			pair->pp_fbcnt = 0;
			read_needed = 1;
		}
	}

	if (read_needed) {
		if (port_associate(g_port, PORT_SOURCE_FD, pair->pp_readfd,
		    POLLIN, pair) < 0) {
			perror("port_associate");
			return (-1);
		}
	}

	if (write_needed) {
		if (port_associate(g_port, PORT_SOURCE_FD, pair->pp_writefd,
		    POLLOUT, pair) < 0) {
			perror("port_associate");
			return (-1);
		}
	}

	return (0);

}

static void *
proxy_thread_loop(void *arg)
{
	port_event_t ev;
	struct proxy_user *pu;
	int timeouts = 0;
	timespec_t tmot;
	boolean_t timed_out = B_FALSE;
	boolean_t should_exit = B_FALSE;

	for (;;) {
		tmot.tv_sec = DEFAULT_TIMEOUT;
		tmot.tv_nsec = 0;

		if (port_get(g_port, &ev, &tmot) < 0) {
			if (errno == ETIME) {
				timed_out = B_TRUE;
				timeouts++;
			} else {
				/*
				 * Unexpected error.  Adjust thread
				 * bean counters and exit.
				 */
				(void) mutex_lock(g_thr_pool_lock);
				g_tp_exited_threads++;
				g_tp_running_threads--;
				(void) cond_signal(&g_thr_pool_cv);
				(void) mutex_unlock(g_thr_pool_lock);
				perror("port_get");
				thr_exit(NULL);
			}
		} else {
			timeouts = 0;
		}

		/*
		 * Reached timeout count. Check to see if thread
		 * should exit.
		 */
		if (timed_out && timeouts > TIMEOUT_COUNT) {
			(void) mutex_lock(g_thr_pool_lock);
			if ((g_proxy_pair_count < g_tp_running_threads) &&
			    (g_tp_running_threads > g_tp_min_threads)) {
				g_tp_exited_threads++;
				g_tp_running_threads--;
				should_exit = B_TRUE;
				(void) cond_signal(&g_thr_pool_cv);
			}
			(void) mutex_unlock(g_thr_pool_lock);

			if (should_exit) {
				thr_exit(NULL);
			}

			/*
			 * Reached timeout count, but not allowed to
			 * exit.  Reset counters and continue.
			 */
			timed_out = B_FALSE;
			timeouts = 0;
			continue;
		} else if (timed_out) {
			/*
			 * If port_get timed out, but this thread hasn't
			 * reached its timeout count just continue.
			 */
			timed_out = B_FALSE;
			continue;
		}

		/*
		 * Event handling code.  This is what we do when we don't
		 * timeout.
		 */
		if (ev.portev_source == PORT_SOURCE_FD) {
			pu = (struct proxy_user *)ev.portev_user;
			pu->pu_callback(pu, &ev);
		} else {
			/*
			 * Exit requested. Don't bother adjusting counters
			 * since cleanup here is handled by main thread,
			 * not manager thread.
			 */
			break;
		}
	}

	return (arg);
}

static int
check_connect(struct proxy_pair *pair)
{
	int error;
	socklen_t len;

	len = sizeof (error);

	if (getsockopt(pair->pp_writefd, SOL_SOCKET, SO_ERROR, &error,
	    &len) < 0) {
		return (-1);
	}

	if (error) {
		errno = error;
		return (-1);
	}

	return (0);
}

static void
proxy_func(struct proxy_pair *pair, port_event_t *ev)
{
	int	rc;

	if (ev->portev_events & (POLLERR | POLLHUP | POLLNVAL)) {
		pair->pp_state = PROXY_STATE_CLOSING;
		shutdown_proxypair(pair);
		return;
	}

	switch (pair->pp_state) {
	case PROXY_STATE_WAIT_CONNECT:
		rc = check_connect(pair);
		if (rc < 0) {
			/* break out early if connect failed */
			break;
		}
		pair->pp_state = PROXY_STATE_WAIT_DATA;
		rc = clone_and_register(pair);
		break;
	case PROXY_STATE_WAIT_DATA:
		rc = send_recv_data(pair);
		break;
	}

	if (rc < 0) {
		pair->pp_state = PROXY_STATE_CLOSING;
		shutdown_proxypair(pair);
	}
}

/* ARGSUSED */
static void
listen_func(struct proxy_listener *listener, port_event_t *ev)
{
	struct proxy_pair	*pair;
	int			newffd;
	int			newbfd;
	int			err_code;
	struct addrinfo		hints;
	struct addrinfo		*ai = NULL;

	/*
	 * Hold listener's lock, check if cleanup has been requested.
	 */
	(void) mutex_lock(&listener->pl_lock);

	/*
	 * pl_closefd is the other half of the pipe that we weren't able
	 * to close before calling door_return.  Close it now, if it's set to
	 * something that's a fd.
	 */
	if (listener->pl_closefd > -1) {
		if (close(listener->pl_closefd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
		listener->pl_closefd = -1;
	}

	if (listener->pl_cleanup) {
		(void) mutex_unlock(&listener->pl_lock);
		zpd_remove_listener(listener);
		return;
	}

	newffd = accept(listener->pl_fd, NULL, 0);
	if (newffd < 0 && (errno == ECONNABORTED || errno == EINTR ||
	    errno == EWOULDBLOCK)) {
		(void) mutex_unlock(&listener->pl_lock);
		goto out;
	} else if (newffd < 0) {
		perror("accept");
		(void) mutex_unlock(&listener->pl_lock);
		(void) zpd_remove_listener(listener);
		return;
	}
	(void) mutex_unlock(&listener->pl_lock);

	pair = alloc_proxy_pair();
	if (pair == NULL) {
		goto out;
	}
	pair->pp_readfd = newffd;

	/* mark newffd as non-blocking */
	if (set_noblocking(newffd) < 0) {
		free_proxy_pair(pair);
		goto out;
	}

	(void) memset(&hints, 0, sizeof (struct addrinfo));
	hints.ai_flags = AI_ADDRCONFIG;
	hints.ai_family = PF_UNSPEC;
	hints.ai_socktype = SOCK_STREAM;

	/* If proxy config has changed, pull the new info into the listener. */
	if (g_proxy_config->pc_gen > listener->pl_gen) {
		(void) mutex_lock(&g_proxy_config->pc_lock);
		free(listener->pl_proxy_host);
		free(listener->pl_proxy_port);
		listener->pl_proxy_host = strdup(g_proxy_config->pc_proxy_host);
		listener->pl_proxy_port = strdup(g_proxy_config->pc_proxy_port);
		if (listener->pl_proxy_host == NULL ||
		    listener->pl_proxy_port == NULL) {
			(void) fprintf(stderr, "Unable to allocate memory for "
			    "listener configuration.\n");
			exit(EXIT_FAILURE);
		}
		listener->pl_gen = g_proxy_config->pc_gen;
		(void) mutex_unlock(&g_proxy_config->pc_lock);
	}

	if ((err_code = getaddrinfo(listener->pl_proxy_host,
	    listener->pl_proxy_port, &hints, &ai)) != 0) {
		(void) fprintf(stderr, "zoneproxyd: Unable to "
		    "perform name lookup\n");
		(void) fprintf(stderr, "%s: %s\n", listener->pl_proxy_host,
		    gai_strerror(err_code));
		free_proxy_pair(pair);
		goto out;
	}

	if ((newbfd = socket(ai->ai_family, SOCK_STREAM, 0)) < 0) {
		perror("socket");
		free_proxy_pair(pair);
		goto out;
	}

	/* mark newbfd as non-blocking */
	if (set_noblocking(newbfd) < 0) {
		if (close(newbfd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
		free_proxy_pair(pair);
		goto out;
	}

	/* Connect to the proxy backend */
	err_code = connect(newbfd, ai->ai_addr, ai->ai_addrlen);
	if (err_code < 0 && errno == EINPROGRESS) {
		pair->pp_state = PROXY_STATE_WAIT_CONNECT;
		pair->pp_writefd = newbfd;
		/* receipt of POLLOUT means we're connected */
		if (port_associate(g_port, PORT_SOURCE_FD, pair->pp_writefd,
		    POLLOUT, pair) < 0) {
			perror("port_associate");
			if (close(newbfd) < 0) {
				perror("close");
				exit(EXIT_FAILURE);
			}
			free_proxy_pair(pair);
			goto out;
		}
	} else if (err_code < 0) {
		/* Error, cleanup */
		if (close(newbfd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
		free_proxy_pair(pair);
		goto out;
	} else {
		/* connected without waiting! */
		pair->pp_state = PROXY_STATE_WAIT_DATA;
		pair->pp_writefd = newbfd;

		if (clone_and_register(pair) < 0) {
			pair->pp_state = PROXY_STATE_CLOSING;
			shutdown_proxypair(pair);
		}

	}

out:
	if (ai) {
		freeaddrinfo(ai);
	}

	/*
	 * Check to make sure that cleanup hasn't been requested before calling
	 * port_associate to get another connection.
	 */
	(void) mutex_lock(&listener->pl_lock);

	if (listener->pl_cleanup) {
		(void) mutex_unlock(&listener->pl_lock);
		zpd_remove_listener(listener);
		return;
	}

	/* re-associate listener; accept further connections */
	if (port_associate(g_port, PORT_SOURCE_FD, listener->pl_fd, POLLIN,
	    listener) < 0) {
		perror("port_associate");
		(void) mutex_unlock(&listener->pl_lock);
		zpd_remove_listener(listener);
		return;
	}
	(void) mutex_unlock(&listener->pl_lock);
}

/* ARGSUSED */
static void *
zpd_door_loop(void *arg)
{
	thread_t *tid;

	/*
	 * If g_door hasn't been set yet, wait for the main thread
	 * to create the door.
	 */
	(void) mutex_lock(g_door_thr_lock);
	while (g_door == -1) {
		(void) cond_wait(g_door_thr_cv, g_door_thr_lock);
	}
	(void) mutex_unlock(g_door_thr_lock);

	/* Bind to door's private pool */
	if (door_bind(g_door) < 0) {
		perror("door_bind");
		return (NULL);
	}

	/*
	 * Disable cancellation.  Solaris threads have no cancellation
	 * mechanism, but are interchangeable with PThreads.  This means we must
	 * use the pthread interface to disable cancellation.
	 */
	(void) pthread_setcancelstate(PTHREAD_CANCEL_DISABLE, NULL);

	/*
	 * Threads use the thr_keycreate interface to register a destructor.
	 * The destructor allows us to decrement the door thread count when a
	 * thread exits.  In order for the destructor to be called, each thread
	 * must register a non-NULL value through thr_setspecfic.  Do this
	 * here.
	 */
	tid = malloc(sizeof (thread_t));
	if (tid == NULL) {
		perror("malloc");
		return (NULL);
	}
	*tid = thr_self();
	(void) thr_setspecific(g_thr_info_key, tid);

	/* Invoke door_return to wait for door_call. */
	(void) door_return(NULL, 0, NULL, 0);
	return (NULL);
}

/* ARGSUSED */
static void
thread_exiting(void *arg)
{
	free(arg);
	(void) mutex_lock(g_door_thr_lock);
	g_door_thread_count--;
	(void) mutex_unlock(g_door_thr_lock);
}

/* ARGSUSED */
static void
zpd_door_create_thread(door_info_t *dip)
{
	int rc;

	/*
	 * Only create threads for DOOR_PRIVATE pools.
	 */
	if (dip == NULL)
		return;

	(void) mutex_lock(g_door_thr_lock);
	if (g_door_thread_count < g_max_door_thread && !g_quit) {
		rc = thr_create(NULL, 0, zpd_door_loop, NULL, THR_DAEMON,
		    NULL);
		if (rc < 0) {
			perror("thr_create");
		} else {
			g_door_thread_count++;
		}
	}
	(void) mutex_unlock(g_door_thr_lock);
}

/*
 * Thread responsible for creating/joining proxy threads
 * during normal operation of zoneproxyd.
 */
static void *
thread_manager(void *arg)
{
	int i;
	int rc;
	int nthr = 0;
	timestruc_t tmo;

	(void) mutex_lock(g_thr_pool_lock);
	g_tp_exited_threads = 0;
	g_tp_running_threads = 0;

	/* Start proxy threads */
	for (i = 0; i < g_tp_min_threads; i++) {
		rc = thr_create(NULL, 0, proxy_thread_loop, NULL,
		    THR_BOUND, NULL);
		if (rc < 0) {
			perror("thr_create");
			exit(EXIT_FAILURE);
		}
		g_tp_running_threads++;
	}

	/* Loop waiting for threads to exit, or need to be started */
	for (;;) {
		if (g_quit == B_TRUE) {
			break;
		}

		while (g_tp_exited_threads > 0) {
			if (thr_join(0, NULL, NULL) < 0) {
				perror("thr_join");
				exit(EXIT_FAILURE);
			}
			g_tp_exited_threads--;
		}

		/* Compute number of threads to create, if any */
		if (g_tp_running_threads < g_tp_min_threads) {
			nthr = g_tp_min_threads - g_tp_running_threads;
		} else if ((g_tp_running_threads < g_tp_max_threads) &&
		    (g_proxy_pair_count > g_tp_running_threads)) {
			nthr = MIN(g_proxy_pair_count,
			    g_tp_max_threads - g_tp_running_threads);
		} else {
			nthr = 0;
		}

		for (i = 0; i < nthr; i++) {
			rc = thr_create(NULL, 0, proxy_thread_loop, NULL,
			    THR_BOUND, NULL);
			if (rc < 0) {
				perror("thr_create");
				exit(EXIT_FAILURE);
			}
			g_tp_running_threads++;
		}

		/* sleep, waiting for timeout or cond_signal */
		tmo.tv_sec = DEFAULT_TIMEOUT;
		tmo.tv_nsec = 0;
		(void) cond_reltimedwait(&g_thr_pool_cv, g_thr_pool_lock, &tmo);
	}
	(void) mutex_unlock(g_thr_pool_lock);

	return (arg);
}

/* Contract stuff for zone_enter() */
static int
init_template(void)
{
	int fd;
	int err = 0;

	fd = open(CTFS_ROOT "/process/template", O_RDWR);
	if (fd == -1)
		return (-1);

	/*
	 * For now, zoneadmd doesn't do anything with the contract.
	 * Deliver no events, don't inherit, and allow it to be orphaned.
	 */
	err |= ct_tmpl_set_critical(fd, 0);
	err |= ct_tmpl_set_informative(fd, 0);
	err |= ct_pr_tmpl_set_fatal(fd, CT_PR_EV_HWERR);
	err |= ct_pr_tmpl_set_param(fd, CT_PR_PGRPONLY | CT_PR_REGENT);
	if (err || ct_tmpl_activate(fd)) {
		if (close(fd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
		return (-1);
	}

	return (fd);
}

/*
 * Contract stuff for zone_enter()
 */
static int
contract_latest(ctid_t *id)
{
	int cfd, r;
	ct_stathdl_t st;
	ctid_t result;

	if ((cfd = open(CTFS_ROOT "/process/latest", O_RDONLY)) == -1)
		return (errno);

	if ((r = ct_status_read(cfd, CTD_COMMON, &st)) != 0) {
		if (close(cfd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
		return (r);
	}

	result = ct_status_get_id(st);
	ct_status_free(st);
	if (close(cfd) < 0) {
		perror("close");
		exit(EXIT_FAILURE);
	}

	*id = result;
	return (0);
}

/*
 * Boilerplate for contract abandon stuff.  This program doesn't currently exec
 * but this is set just in case.
 */
static int
close_on_exec(int fd)
{
	int flags = fcntl(fd, F_GETFD, 0);
	if ((flags != -1) && (fcntl(fd, F_SETFD, flags | FD_CLOEXEC) != -1))
		return (0);
	return (-1);
}

static int
contract_open(ctid_t ctid, const char *type, const char *file, int oflag)
{
	char path[PATH_MAX];
	int n, fd;

	if (type == NULL)
		type = "all";

	n = snprintf(path, PATH_MAX, CTFS_ROOT "/%s/%ld/%s", type, ctid, file);
	if (n >= sizeof (path)) {
		errno = ENAMETOOLONG;
		return (-1);
	}

	fd = open(path, oflag);
	if (fd != -1) {
		if (close_on_exec(fd) == -1) {
			int err = errno;
			if (close(fd) < 0) {
				perror("close");
				exit(EXIT_FAILURE);
			}
			errno = err;
			return (-1);
		}
	}
	return (fd);
}

static int
contract_abandon_id(ctid_t ctid)
{
	int fd, err;

	fd = contract_open(ctid, "all", "ctl", O_WRONLY);
	if (fd == -1)
		return (errno);

	err = ct_ctl_abandon(fd);
	if (close(fd) < 0) {
		perror("close");
		exit(EXIT_FAILURE);
	}

	return (err);
}

static int
do_fattach(int door, char *path, boolean_t detach_only)
{
	int fd;

	(void) fdetach(path);
	(void) unlink(path);
	if (detach_only)
		return (0);
	/* Only priviliged processes should open this file */
	fd = open(path, O_CREAT|O_RDWR, 0600);
	if (fd < 0)
		return (2);
	if (fattach(door, path) != 0)
		return (3);
	if (close(fd) < 0) {
		perror("close");
		exit(EXIT_FAILURE);
	}
	return (0);
}

static void
zpd_fattach_zone(zoneid_t zid, int door, boolean_t detach_only)
{
	char *path = ZP_DOOR_PATH;
	int pid, stat, tmpl_fd;
	ctid_t ct;

	escalate_privs();

	/* Don't bother forking if fattach is happening in the global zone. */
	if (zid == 0) {
		int rc;

		rc = do_fattach(door, path, detach_only);
		if (rc == 2)
			(void) fprintf(stderr,
			    "Unable to create door file: %s\n", path);
		else if (rc == 3)
			(void) fprintf(stderr,
			    "Unable to fattach file: %s\n", path);
		drop_privs();
		return;
	}

	if ((tmpl_fd = init_template()) == -1) {
		(void) fprintf(stderr, "Unable to init template\n");
		drop_privs();
		return;
	}

	pid = fork1();
	if (pid < 0) {
		(void) ct_tmpl_clear(tmpl_fd);
		(void) fprintf(stderr,
		    "Can't fork to add zoneproxy door to zoneid %ld\n", zid);
		drop_privs();
		return;
	}

	if (pid == 0) {
		(void) ct_tmpl_clear(tmpl_fd);
		if (close(tmpl_fd) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
		if (zone_enter(zid) != 0) {
			if (errno == EINVAL) {
				_exit(EXIT_SUCCESS);
			}
			_exit(EXIT_FAILURE);
		}
		_exit(do_fattach(door, path, detach_only));
	}
	if (contract_latest(&ct) == -1)
		ct = -1;
	(void) ct_tmpl_clear(tmpl_fd);
	if (close(tmpl_fd) < 0) {
		perror("close");
		exit(EXIT_FAILURE);
	}
	(void) contract_abandon_id(ct);
	while (waitpid(pid, &stat, 0) != pid)
		;
	if (WIFEXITED(stat) && WEXITSTATUS(stat) == 0) {
		drop_privs();
		return;
	}

	(void) fprintf(stderr, "Unable to attach door to zoneid: %ld\n", zid);

	if (WEXITSTATUS(stat) == 1)
		(void) fprintf(stderr, "Cannot enter zone\n");
	else if (WEXITSTATUS(stat) == 2)
		(void) fprintf(stderr, "Unable to create door file: %s\n",
		    path);
	else if (WEXITSTATUS(stat) == 3)
		(void) fprintf(stderr, "Unable to fattach file: %s\n", path);

	(void) fprintf(stderr, "Internal error entering zone: %ld\n", zid);
	drop_privs();
}

static void
fattach_all_zones(boolean_t detach_only)
{
	zoneid_t *zids;
	uint_t nzids;
	int i;

	if (zone_get_zoneids(&zids, &nzids) != 0) {
		(void) fprintf(stderr, "Could not get list of zones");
		return;
	}

	for (i = 0; i < nzids; i++)
		zpd_fattach_zone(zids[i], g_door, detach_only);
	free(zids);
}

static void
close_door_descs(door_desc_t *dp, uint_t ndesc)
{
	int fd;

	while (ndesc > 0) {
		fd = dp->d_data.d_desc.d_descriptor;
		if (dp->d_attributes & DOOR_DESCRIPTOR) {
			if (close(fd) < 0) {
				perror("close");
				exit(EXIT_FAILURE);
			}
		}
		dp++;
		ndesc--;
	}
}

static int
zpd_perm_check(int cmd, zoneid_t zid)
{
	ucred_t *ucred;
	zoneid_t uzid;

	ucred = alloca(ucred_size());
	if (door_ucred(&ucred) != 0) {
		return (-1);
	}

	uzid = ucred_getzoneid(ucred);

	/*
	 * Enforce the following permission checks:
	 *
	 * If the command is ADD/REMOVE zone, the caller must be the global
	 * zone.
	 *
	 * If the command is NEW_LISTENER, the caller must be a non-global zone
	 * and the supplied zoneid must match the caller's zoneid.
	 */

	switch (cmd) {
	case ZP_CMD_PING:
		/* Always OK to ping */
		return (0);
	case ZP_CMD_REMOVE_LISTENER:
	case ZP_CMD_NEW_LISTENER:
		if (uzid == 0) {
			return (-1);
		}
		if (uzid != zid) {
			return (-1);
		}
		return (0);
	case ZP_CMD_ZONE_ADDED:
	case ZP_CMD_ZONE_REMOVED:
		if (uzid != 0) {
			return (-1);
		}
		return (0);
	default:
		break;
	}

	return (-1);
}

static struct proxy_listener *
zpd_find_listener(zoneid_t zid)
{
	struct proxy_listener *wl;

	for (wl = TAILQ_FIRST(&zone_listener_list); wl != NULL;
	    wl = TAILQ_NEXT(wl, pl_list_link)) {

		if (wl->pl_zid == zid)
			return (wl);
	}

	return (NULL);
}

static int
zpd_add_listener(zoneid_t zid, int fd, int pipefd, int closefd)
{
	struct proxy_listener *old_listener;
	struct proxy_listener *listener;

	(void) mutex_lock(g_listener_lock);
	old_listener = zpd_find_listener(zid);
	if (old_listener) {
		zpd_listener_cleanup(old_listener);
	}

	listener = alloc_proxy_listener();
	if (listener == NULL) {
		goto fail;
	}
	listener->pl_fd = fd;
	listener->pl_zid = zid;
	listener->pl_pipefd = pipefd;
	listener->pl_closefd = closefd;
	TAILQ_INSERT_TAIL(&zone_listener_list, listener, pl_list_link);
	if (set_noblocking(fd) < 0) {
		goto fail;
	}
	if (set_noblocking(pipefd) < 0) {
		goto fail;
	}
	if (port_associate(g_port, PORT_SOURCE_FD, listener->pl_fd, POLLIN,
	    listener) < 0) {
		perror("port_associate");
		goto fail;
	}
	(void) mutex_unlock(g_listener_lock);
	return (0);

fail:
	if (listener) {
		/* No cleanup required, since list lock was never dropped */
		TAILQ_REMOVE(&zone_listener_list, listener, pl_list_link);
		free_proxy_listener(listener);
	}
	(void) mutex_unlock(g_listener_lock);
	return (-1);
}

/*
 * This method has to perform an intricate dance to cleanup a listener.  If it
 * is able to dissociate the listener from the port, it may remove the listener.
 * Otherwise, it must set the cleanup flag and let the thread running the
 * listener perform the removal.
 *
 * Caller should hold the listener list lock.
 */
static void
zpd_listener_cleanup(struct proxy_listener *listener)
{
	int rc;
	struct proxy_listener *wl;

	(void) mutex_lock(&listener->pl_lock);
	if (listener->pl_cleanup) {
		(void) mutex_unlock(&listener->pl_lock);
		return;
	}

	for (wl = TAILQ_FIRST(&zone_listener_list); wl != NULL;
	    wl = TAILQ_NEXT(wl, pl_list_link)) {
		if (wl == listener) {
			TAILQ_REMOVE(&zone_listener_list, listener,
			    pl_list_link);
			break;
		}
	}
	rc = port_dissociate(g_port, PORT_SOURCE_FD, listener->pl_fd);
	if (rc == 0) {
		/* successfully got the object, remove it. */
		(void) mutex_unlock(&listener->pl_lock);
		free_proxy_listener(listener);
		return;
	} else if (rc < 0 && errno == ENOENT) {
		/*
		 * Didn't find the event associated with the port. Another
		 * thread must be concurrently processing events for the
		 * fd.
		 */
		listener->pl_cleanup = B_TRUE;
	} else {
		/* Unexpected error */
		perror("port_dissociate");
		exit(EXIT_FAILURE);
	}
	(void) mutex_unlock(&listener->pl_lock);
}

static void
zpd_remove_listener(struct proxy_listener *listener)
{
	struct proxy_listener *wl;

	/*
	 * Add and remove operations hold the list lock for the duration of
	 * their execution.  When this routine acquires the list lock and
	 * removes the listener, it should no longer be reachable by any other
	 * thread.
	 */
	(void) mutex_lock(g_listener_lock);
	for (wl = TAILQ_FIRST(&zone_listener_list); wl != NULL;
	    wl = TAILQ_NEXT(wl, pl_list_link)) {
		if (wl == listener) {
			TAILQ_REMOVE(&zone_listener_list, listener,
			    pl_list_link);
			break;
		}
	}

	(void) mutex_unlock(g_listener_lock);

	free_proxy_listener(listener);
}

/*
 * Zone removal call.  This routine cannot fdetach the door in the zone because
 * the zone is in shutdown state and cannot be zone_enter'd.  This means that
 * the add_zone code must always fdetach and unlink the existing door before
 * creating a new one.
 */
static int
zpd_remove_zone(zoneid_t zid)
{
	struct proxy_listener *listener;

	(void) mutex_lock(g_listener_lock);
	listener = zpd_find_listener(zid);
	if (listener) {
		zpd_listener_cleanup(listener);
	}
	(void) mutex_unlock(g_listener_lock);

	return (0);
}

/* ARGSUSED */
static void
zpd_door_server(void *cookie, char *argp, size_t arg_size,
    door_desc_t *dp, uint_t n_desc)
{
	int *args, cmd;
	int pipefd[2];
	uint_t nexpected_desc;
	door_desc_t *r_dp = NULL;
	door_desc_t rdesc;
	uint_t r_n_desc = 0;

	if (argp == DOOR_UNREF_DATA) {
		(void) door_return(NULL, 0, NULL, 0);
	}

	if (arg_size != sizeof (cmd) * 2) {
		close_door_descs(dp, n_desc);
		(void) door_return(NULL, 0, NULL, 0);
	}

	/* LINTED */
	args = (int *)argp;
	cmd = args[0];

	/*
	 * Caller may have passed more descriptors than expected.
	 * If so, close the extraneous fds.
	 */
	nexpected_desc = (cmd == ZP_CMD_NEW_LISTENER) ? 1 : 0;
	if (n_desc > nexpected_desc) {
		close_door_descs(dp + nexpected_desc, n_desc - nexpected_desc);
	}

	switch (cmd) {
	case ZP_CMD_NEW_LISTENER:
		if (zpd_perm_check(cmd, args[1]) < 0) {
			close_door_descs(dp, n_desc);
			args[1] = ZP_STATUS_PERMISSION;
			goto out;
		}
		if (n_desc < 1 || (dp->d_attributes & DOOR_DESCRIPTOR) == 0) {
			args[1] = ZP_STATUS_INVALID;
			goto out;
		}
		if (pipe(pipefd) < 0) {
			args[1] = ZP_STATUS_ERROR;
			goto out;
		}
		if (zpd_add_listener(args[1],
		    dp->d_data.d_desc.d_descriptor, pipefd[0], pipefd[1]) < 0) {
			close_door_descs(dp, n_desc);
			if (close(pipefd[0]) < 0) {
				perror("close");
				exit(EXIT_FAILURE);
			}
			if (close(pipefd[1]) < 0) {
				perror("close");
				exit(EXIT_FAILURE);
			}
			args[1] = ZP_STATUS_ERROR;
			goto out;
		}

		r_dp = &rdesc;
		r_dp->d_attributes = DOOR_DESCRIPTOR;
		r_dp->d_data.d_desc.d_descriptor = pipefd[1];
		r_n_desc = 1;
		args[1] = ZP_STATUS_OK;
		break;
	case ZP_CMD_ZONE_ADDED:
		if (zpd_perm_check(cmd, args[1]) < 0) {
			args[1] = ZP_STATUS_PERMISSION;
			goto out;
		}
		zpd_fattach_zone(args[1], g_door, B_FALSE);
		args[1] = ZP_STATUS_OK;
		break;
	case ZP_CMD_REMOVE_LISTENER:
	case ZP_CMD_ZONE_REMOVED:
		if (zpd_perm_check(cmd, args[1]) < 0) {
			args[1] = ZP_STATUS_PERMISSION;
			goto out;
		}
		if (zpd_remove_zone(args[1]) < 0) {
			args[1] = ZP_STATUS_ERROR;
			goto out;
		}
		args[1] = ZP_STATUS_OK;
		break;
	case ZP_CMD_PING:
		if (zpd_perm_check(cmd, args[1]) < 0) {
			args[1] = ZP_STATUS_PERMISSION;
			goto out;
		}
		args[1] = ZP_STATUS_OK;
		break;
	default:
		args[1] = ZP_STATUS_UNKNOWN;
		break;
	}
out:
	(void) door_return(argp, sizeof (cmd) * 2, r_dp, r_n_desc);
}

static void
daemonize_ready(char status)
{
	/*
	 * wake the parent with a clue
	 */
	(void) write(g_pipe_fd, &status, 1);
	if (close(g_pipe_fd) < 0) {
		perror("close");
		exit(EXIT_FAILURE);
	}
}

static int
daemonize_start(void)
{
	char data;
	int status;

	int filedes[2];
	pid_t pid;

	if (close(0) < 0) {
		perror("close");
		exit(EXIT_FAILURE);
	}
	if (dup2(2, 1) < 0) {
		perror("dup2");
		exit(EXIT_FAILURE);
	}

	if (pipe(filedes) < 0)
		return (-1);

	(void) fflush(NULL);

	if ((pid = fork1()) < 0)
		return (-1);

	if (pid != 0) {
		/*
		 * parent
		 */
		if (close(filedes[1]) < 0) {
			perror("close");
			exit(EXIT_FAILURE);
		}
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
	if (close(filedes[0]) < 0) {
		perror("close");
		exit(EXIT_FAILURE);
	}

	/*
	 * generic Unix setup
	 */
	(void) setsid();
	(void) umask(0000);

	return (0);
}

static void
drop_privs(void)
{
	priv_set_t *ePrivSet = NULL;
	priv_set_t *lPrivSet = NULL;

	if ((ePrivSet = priv_str_to_set("basic", ",", NULL)) == NULL) {
		(void) fprintf(stderr, "Unable to get 'basic' privset\n");
		exit(EXIT_FAILURE);
	}

	/* Drop any privs out of the basic set that we won't need */
	(void) priv_delset(ePrivSet, PRIV_FILE_LINK_ANY);
	(void) priv_delset(ePrivSet, PRIV_PROC_INFO);
	(void) priv_delset(ePrivSet, PRIV_PROC_SESSION);
	(void) priv_delset(ePrivSet, PRIV_PROC_EXEC);

	/* Add privs needed for daemon operation */
	(void) priv_addset(ePrivSet, PRIV_CONTRACT_EVENT);
	(void) priv_addset(ePrivSet, PRIV_CONTRACT_IDENTITY);

	/* Set effective set */
	if (setppriv(PRIV_SET, PRIV_EFFECTIVE, ePrivSet) != 0) {
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
	priv_freeset(ePrivSet);

}

/*
 * zone_enter requires that the process have the full privilege set.  We try to
 * run with the lowest possible set, but in the case where we zone-enter, we
 * must re-set the effective set to be all privs.
 */
static void
escalate_privs(void)
{
	priv_set_t *ePrivSet = NULL;

	if ((ePrivSet = priv_allocset()) == NULL) {
		(void) fprintf(stderr, "Unable to allocate privset\n");
		exit(EXIT_FAILURE);
	}

	priv_fillset(ePrivSet);

	if (setppriv(PRIV_SET, PRIV_EFFECTIVE, ePrivSet) != 0) {
		(void) fprintf(stderr, "Unable to set effective priv set\n");
		exit(EXIT_FAILURE);
	}

	priv_freeset(ePrivSet);
}

static struct proxy_config *
config_alloc(void)
{
	struct proxy_config *pc = NULL;

	if ((pc = malloc(sizeof (struct proxy_config))) == NULL)
		return (NULL);

	(void) memset(pc, 0, sizeof (struct proxy_config));

	if (mutex_init(&pc->pc_lock, USYNC_THREAD, NULL) < 0) {
		goto out;
	}

	if ((pc->pc_hdl = scf_handle_create(SCF_VERSION)) == NULL) {
		goto out;
	}

	if ((pc->pc_inst = scf_instance_create(pc->pc_hdl)) == NULL) {
		goto out;
	}

	if ((pc->pc_pg = scf_pg_create(pc->pc_hdl)) == NULL) {
		goto out;
	}

	if ((pc->pc_prop = scf_property_create(pc->pc_hdl)) == NULL) {
		goto out;
	}

	if ((pc->pc_val = scf_value_create(pc->pc_hdl)) == NULL) {
		goto out;
	}

	if ((pc->pc_proxy_host = strdup(DEFAULT_HOST)) == NULL) {
		goto out;
	}

	if ((pc->pc_proxy_port = strdup(DEFAULT_PORT)) == NULL) {
		goto out;
	}

	pc->pc_gen = 1;

	return (pc);

out:
	config_free(pc);
	return (NULL);
}

static void
config_free(struct proxy_config *pc)
{
	if (pc == NULL)
		return;

	if (pc->pc_inst != NULL) {
		scf_instance_destroy(pc->pc_inst);
	}

	if (pc->pc_pg != NULL) {
		scf_pg_destroy(pc->pc_pg);
	}

	if (pc->pc_prop != NULL) {
		scf_property_destroy(pc->pc_prop);
	}

	if (pc->pc_val != NULL) {
		scf_value_destroy(pc->pc_val);
	}

	if (pc->pc_hdl != NULL) {
		scf_handle_destroy(pc->pc_hdl);
	}

	free(pc->pc_proxy_host);
	free(pc->pc_proxy_port);

	(void) mutex_destroy(&pc->pc_lock);
	free(pc);
}

static int
config_read(struct proxy_config *pc)
{
	char *host = NULL;
	char *port = NULL;

	if ((host = malloc(CONF_STR_SZ)) == NULL) {
		goto fail;
	}

	if ((port = malloc(CONF_STR_SZ)) == NULL) {
		goto fail;
	}

	(void) mutex_lock(&pc->pc_lock);

	if (scf_handle_bind(pc->pc_hdl) != 0) {
		(void) fprintf(stderr, "scf_handle_bind failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_handle_decode_fmri(pc->pc_hdl, SYSREPO_FMRI, NULL, NULL,
	    pc->pc_inst, NULL, NULL, SCF_DECODE_FMRI_REQUIRE_INSTANCE) != 0) {
		(void) fprintf(stderr, "scf_handle_decode_fmri failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_instance_get_pg(pc->pc_inst, SYSREPO_PG, pc->pc_pg) != 0) {
		(void) fprintf(stderr, "scf_instance_get_pg failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_pg_get_property(pc->pc_pg, SYSREPO_HOST, pc->pc_prop) != 0) {
		(void) fprintf(stderr, "scf_pg_get_property failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_property_get_value(pc->pc_prop, pc->pc_val) != 0) {
		(void) fprintf(stderr, "scf_property_get_value failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_value_get_as_string_typed(pc->pc_val, SCF_TYPE_ASTRING,
	    host, CONF_STR_SZ) < 0) {
		(void) fprintf(stderr,
		    "scf_value_get_as_string_typed failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_pg_get_property(pc->pc_pg, SYSREPO_PORT, pc->pc_prop) != 0) {
		(void) fprintf(stderr, "scf_pg_get_property failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_property_get_value(pc->pc_prop, pc->pc_val) != 0) {
		(void) fprintf(stderr, "scf_property_get_value failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_value_get_as_string_typed(pc->pc_val, SCF_TYPE_COUNT,
	    port, CONF_STR_SZ) < 0) {
		(void) fprintf(stderr,
		    "scf_value_get_as_string_typed failed; %s\n",
		    scf_strerror(scf_error()));
		goto fail;
	}

	if (scf_handle_unbind(pc->pc_hdl) != 0) {
		(void) fprintf(stderr, "scf_handle_unbind failed; %s\n",
		    scf_strerror(scf_error()));
	}

	free(pc->pc_proxy_host);
	free(pc->pc_proxy_port);
	pc->pc_proxy_host = host;
	pc->pc_proxy_port = port;
	pc->pc_gen++;
	(void) mutex_unlock(&pc->pc_lock);
	return (0);

fail:
	(void) mutex_unlock(&pc->pc_lock);
	free(host);
	free(port);
	return (-1);
}

static void
s_handler(void)
{
	sigset_t get_sigs;
	int rc;

	(void) sigfillset(&get_sigs);
	while (g_quit == B_FALSE) {
		rc = sigwait(&get_sigs);

		if (rc == SIGINT || rc == SIGTERM || rc == SIGHUP) {
			(void) mutex_lock(&g_quit_lock);
			g_quit = B_TRUE;
			(void) cond_signal(&g_quit_cv);
			(void) mutex_unlock(&g_quit_lock);
		}

		if (g_config_smf && rc == SIGUSR1) {
			if (config_read(g_proxy_config) != 0) {
				(void) fprintf(stderr, "Unable to re-load "
				    "proxy configuration from SMF.\n");
			}
		}
	}
}

int
main(int argc, char **argv)
{
	extern char *optarg;
	char *proxystr = NULL;
	char *proxy_host, *proxy_port;
	int rc;
	int ncpu;
	struct proxy_listener *wl;
	sigset_t blockset;
	struct rlimit rlp = {0};

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

	g_config_smf = (proxystr == NULL) ? B_TRUE : B_FALSE;

	if (!g_config_smf) {
		proxy_host = strtok(proxystr, ":");
		if (proxy_host == NULL) {
			(void) fprintf(stderr,
			    "host must be of format hostname:port\n");
			usage();
		}
		proxy_port = strtok(NULL, ":");
		if (proxy_port == NULL) {
			(void) fprintf(stderr,
			    "host must be of format hostname:port\n");
			usage();
		}
	}

	g_quit = B_FALSE;
	(void) signal(SIGPIPE, SIG_IGN);

	if ((g_proxy_config = config_alloc()) == NULL) {
		(void) fprintf(stderr, "Unable to allocate proxy config\n");
		exit(EXIT_FAILURE);
	}

	if (g_config_smf) {
		if (config_read(g_proxy_config) != 0) {
			(void) fprintf(stderr, "Unable to read proxy config. "
			    "Falling back to defaults.\n");
		}
	} else {
		free(g_proxy_config->pc_proxy_host);
		free(g_proxy_config->pc_proxy_port);
		g_proxy_config->pc_proxy_host = strdup(proxy_host);
		g_proxy_config->pc_proxy_port = strdup(proxy_port);
		if (g_proxy_config->pc_proxy_host == NULL ||
		    g_proxy_config->pc_proxy_port == NULL) {
			(void) fprintf(stderr, "Unable to allocate memory for "
			    "proxy configuration strings\n");
			exit(EXIT_FAILURE);
		}
	}

	if (daemonize_start() < 0)
		(void) fprintf(stderr, "Unable to start daemon\n");

	/* Increase the number of maximum file descriptors */
	(void) getrlimit(RLIMIT_NOFILE, &rlp);
	if (rlp.rlim_cur < MAX_FDS_DEFAULT)
		rlp.rlim_cur = MAX_FDS_DEFAULT;
	if (rlp.rlim_max < rlp.rlim_cur)
		rlp.rlim_max = rlp.rlim_cur;
	if (setrlimit(RLIMIT_NOFILE, &rlp) < 0) {
		perror("setrlimit");
		exit(EXIT_FAILURE);
	}

	drop_privs();

	(void) sigfillset(&blockset);

	if (thr_sigsetmask(SIG_BLOCK, &blockset, NULL) < 0) {
		perror("thr_sigsetmask");
		exit(EXIT_FAILURE);
	}

	/* Create single global event port */
	if ((g_port = port_create()) < 0) {
		perror("port_create");
		exit(EXIT_FAILURE);
	}

	/* Setup listener list. */
	TAILQ_INIT(&zone_listener_list);

	/* Initialize locks */
	g_door_thr_lock = memalign(DEFAULT_LOCK_ALIGN, sizeof (mutex_t));
	if (g_door_thr_lock == NULL) {
		(void) fprintf(stderr, "Unable to allocate g_door_thr_lock\n");
		exit(EXIT_FAILURE);
	}
	if (mutex_init(g_door_thr_lock, USYNC_THREAD, NULL) < 0) {
		perror("mutex_init");
		exit(EXIT_FAILURE);
	}

	g_door_thr_cv = memalign(DEFAULT_LOCK_ALIGN, sizeof (cond_t));
	if (g_door_thr_cv == NULL) {
		(void) fprintf(stderr, "Unable to allocate g_door_thr_cv\n");
		exit(EXIT_FAILURE);
	}
	if (cond_init(g_door_thr_cv, USYNC_THREAD, NULL) < 0) {
		perror("cond_init");
		exit(EXIT_FAILURE);
	}

	g_listener_lock = memalign(DEFAULT_LOCK_ALIGN, sizeof (mutex_t));
	if (g_listener_lock == NULL) {
		(void) fprintf(stderr, "Unable to allocate g_listener_lock\n");
		exit(EXIT_FAILURE);
	}
	if (mutex_init(g_listener_lock, USYNC_THREAD, NULL) < 0) {
		perror("mutex_init");
		exit(EXIT_FAILURE);
	}

	g_thr_pool_lock = memalign(DEFAULT_LOCK_ALIGN, sizeof (mutex_t));
	if (g_thr_pool_lock == NULL) {
		(void) fprintf(stderr, "Unable to alloc g_thr_pool_lock\n");
		exit(EXIT_FAILURE);
	}
	if (mutex_init(g_thr_pool_lock, USYNC_THREAD, NULL) < 0) {
		perror("mutex_init");
		exit(EXIT_FAILURE);
	}

	if (thr_keycreate(&g_thr_info_key, thread_exiting) < 0) {
		perror("thr_keycreate");
		exit(EXIT_FAILURE);
	}

	/* Auto-tune min/max threads based upon number of cpus in system */
	ncpu = sysconf(_SC_NPROCESSORS_ONLN);
	if (ncpu < 0) {
		perror("sysconf");
		exit(EXIT_FAILURE);
	}

	/* Paranoia. */
	if (ncpu == 0) {
		(void) fprintf(stderr, "0 cpus online. How is this running?\n");
		exit(EXIT_FAILURE);
	}

	g_tp_min_threads = MIN(g_tp_min_threads, ncpu);
	g_tp_max_threads = MAX(g_tp_max_threads, ncpu/4);

	/* Setup door */
	(void) door_server_create(zpd_door_create_thread);

	(void) mutex_lock(g_door_thr_lock);
	g_door = door_create(zpd_door_server, NULL,
	    DOOR_PRIVATE | DOOR_NO_CANCEL);
	if (g_door < 0) {
		(void) mutex_unlock(g_door_thr_lock);
		perror("door_create");
		exit(EXIT_FAILURE);
	}
	(void) cond_broadcast(g_door_thr_cv);
	(void) mutex_unlock(g_door_thr_lock);

	/*
	 * Set a limit on the size of the data that may be passed
	 * through the door, as well as the number of FDs that may be passed in
	 * any particular call.
	 */
	if (door_setparam(g_door, DOOR_PARAM_DATA_MAX, sizeof (int) * 2) < 0) {
		perror("door_setparam");
		exit(EXIT_FAILURE);
	}
	if (door_setparam(g_door, DOOR_PARAM_DESC_MAX, 1) < 0) {
		perror("door_setparam");
		exit(EXIT_FAILURE);
	}

	fattach_all_zones(B_FALSE);

	/* start signal handling thread */
	rc = thr_create(NULL, 0, (void *(*)(void *))s_handler, NULL,
	    THR_BOUND, NULL);
	if (rc < 0) {
		perror("thr_create");
		exit(EXIT_FAILURE);
	}

	/* Start thread pool manager */
	rc = thr_create(NULL, 0, thread_manager, NULL, THR_BOUND, NULL);
	if (rc < 0) {
		perror("thr_create");
		exit(EXIT_FAILURE);
	}

	daemonize_ready(0);

	/* Wait for signal handling thread to notify us to quit */
	while (g_quit == B_FALSE) {
		(void) mutex_lock(&g_quit_lock);
		(void) cond_wait(&g_quit_cv, &g_quit_lock);
		(void) mutex_unlock(&g_quit_lock);
	}

	/* Wake up manager thread, so it will exit */
	(void) mutex_lock(g_thr_pool_lock);
	(void) cond_signal(&g_thr_pool_cv);
	(void) mutex_unlock(g_thr_pool_lock);

	/* set port alert to wake any sleeping threads */
	if (port_alert(g_port, PORT_ALERT_SET, 1, NULL) < 0) {
		perror("port_alert");
		exit(EXIT_FAILURE);
	}

	/* detach doors */
	fattach_all_zones(B_TRUE);

	(void) door_revoke(g_door);
	if (close(g_port) < 0) {
		perror("close");
		exit(EXIT_FAILURE);
	}

	/* Wait for threads to exit */
	while (thr_join(0, NULL, NULL) == 0)
		;

	/*
	 * Tell any waiting listeners that we're quitting.  Walk the
	 * listener list, writing a byte to each pipe.  Then teardown
	 * any remaining listener structures.
	 */
	(void) mutex_lock(g_listener_lock);
	while (!TAILQ_EMPTY(&zone_listener_list)) {
		char pipeval = '0';

		wl = TAILQ_FIRST(&zone_listener_list);
		TAILQ_REMOVE(&zone_listener_list, wl, pl_list_link);
		(void) write(wl->pl_pipefd, &pipeval, 1);
		free_proxy_listener(wl);
	}
	(void) mutex_unlock(g_listener_lock);

	config_free(g_proxy_config);

	(void) mutex_destroy(g_door_thr_lock);
	(void) mutex_destroy(g_listener_lock);
	(void) mutex_destroy(g_thr_pool_lock);
	(void) cond_destroy(g_door_thr_cv);
	free(g_door_thr_cv);
	free(g_door_thr_lock);
	free(g_listener_lock);
	free(g_thr_pool_lock);

	return (0);
}
