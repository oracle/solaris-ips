#!/usr/bin/python2.7
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

#
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

import getopt
import gettext
import hashlib
import locale
import os
import shutil
import sys
import tempfile
import traceback

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from imp import reload

import pkg
import pkg.actions as actions
import pkg.client.api_errors as api_errors
import pkg.client.transport.transport as transport
import pkg.digest as digest
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.publish.transaction as trans
from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
from pkg.misc import emsg, msg, PipeError

PKG_CLIENT_NAME = "pkgsign"

# pkg exit codes
EXIT_OK      = 0
EXIT_OOPS    = 1
EXIT_BADOPT  = 2
EXIT_PARTIAL = 3

repo_cache = {}

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "{0}: {1}".format(cmd, text)

        else:
                text = "{0}: {1}".format(PKG_CLIENT_NAME, text)


        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + text_nows)

def usage(usage_error=None, cmd=None, retcode=EXIT_BADOPT):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error, cmd=cmd)
        emsg (_("""\
Usage:
        pkgsign -s path_or_uri [-acikn] [--no-index] [--no-catalog]
            (fmri|pattern) ...
"""))

        sys.exit(retcode)

def fetch_catalog(src_pub, xport, temp_root):
        """Fetch the catalog from src_uri."""

        if not src_pub.meta_root:
                # Create a temporary directory for catalog.
                cat_dir = tempfile.mkdtemp(dir=temp_root)
                src_pub.meta_root = cat_dir

        src_pub.transport = xport
        src_pub.refresh(True, True)

        return src_pub.catalog

def __make_tmp_cert(d, pth):
        try:
                with open(pth, "rb") as f:
                        cert = x509.load_pem_x509_certificate(f.read(),
                            default_backend())
        except (ValueError, IOError) as e:
                raise api_errors.BadFileFormat(_("The file {0} was expected to "
                    "be a PEM certificate but it could not be read.").format(
                    pth))
        fd, fp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "wb") as fh:
                fh.write(cert.public_bytes(serialization.Encoding.PEM))
        return fp

def main_func():
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())
        global_settings.client_name = "pkgsign"

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "a:c:i:k:ns:D:",
                    ["help", "no-index", "no-catalog"])
        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))

        show_usage = False
        sig_alg = "rsa-sha256"
        cert_path = None
        key_path = None
        chain_certs = []
        add_to_catalog = True
        set_alg = False
        dry_run = False

        repo_uri = os.getenv("PKG_REPO", None)
        for opt, arg in opts:
                if opt == "-a":
                        sig_alg = arg
                        set_alg = True
                elif opt == "-c":
                        cert_path = os.path.abspath(arg)
                        if not os.path.isfile(cert_path):
                                usage(_("{0} was expected to be a certificate "
                                    "but isn't a file.").format(cert_path))
                elif opt == "-i":
                        p = os.path.abspath(arg)
                        if not os.path.isfile(p):
                                usage(_("{0} was expected to be a certificate "
                                    "but isn't a file.").format(p))
                        chain_certs.append(p)
                elif opt == "-k":
                        key_path = os.path.abspath(arg)
                        if not os.path.isfile(key_path):
                                usage(_("{0} was expected to be a key file "
                                    "but isn't a file.").format(key_path))
                elif opt == "-n":
                        dry_run = True
                elif opt == "-s":
                        repo_uri = misc.parse_uri(arg)
                elif opt == "--help":
                        show_usage = True
                elif opt == "--no-catalog":
                        add_to_catalog = False
                elif opt == "-D":
                        try:
                                key, value = arg.split("=", 1)
                                DebugValues.set_value(key, value)
                        except (AttributeError, ValueError):
                                error(_("{opt} takes argument of form "
                                    "name=value, not {arg}").format(
                                    opt=opt, arg=arg))
        if show_usage:
                usage(retcode=EXIT_OK)

        if not repo_uri:
                usage(_("a repository must be provided"))

        if key_path and not cert_path:
                usage(_("If a key is given to sign with, its associated "
                    "certificate must be given."))

        if cert_path and not key_path:
                usage(_("If a certificate is given, its associated key must be "
                    "given."))

        if chain_certs and not cert_path:
                usage(_("Intermediate certificates are only valid if a key "
                    "and certificate are also provided."))

        if not pargs:
                usage(_("At least one fmri or pattern must be provided to "
                    "sign."))

        if not set_alg and not key_path:
                sig_alg = "sha256"

        s, h = actions.signature.SignatureAction.decompose_sig_alg(sig_alg)
        if h is None:
                usage(_("{0} is not a recognized signature algorithm.").format(
                    sig_alg))
        if s and not key_path:
                usage(_("Using {0} as the signature algorithm requires that a "
                    "key and certificate pair be presented using the -k and -c "
                    "options.").format(sig_alg))
        if not s and key_path:
                usage(_("The {0} hash algorithm does not use a key or "
                    "certificate.  Do not use the -k or -c options with this "
                    "algorithm.").format(sig_alg))

        if DebugValues:
                reload(digest)

        errors = []

        t = misc.config_temp_root()
        temp_root = tempfile.mkdtemp(dir=t)
        del t

        cache_dir = tempfile.mkdtemp(dir=temp_root)
        incoming_dir = tempfile.mkdtemp(dir=temp_root)
        chash_dir = tempfile.mkdtemp(dir=temp_root)
        cert_dir = tempfile.mkdtemp(dir=temp_root)

        try:
                chain_certs = [
                    __make_tmp_cert(cert_dir, c) for c in chain_certs
                ]
                if cert_path is not None:
                        cert_path = __make_tmp_cert(cert_dir, cert_path)

                xport, xport_cfg = transport.setup_transport()
                xport_cfg.add_cache(cache_dir, readonly=False)
                xport_cfg.incoming_root = incoming_dir

                # Configure publisher(s)
                transport.setup_publisher(repo_uri, "source", xport,
                    xport_cfg, remote_prefix=True)
                pats = pargs
                successful_publish = False

                concrete_fmris = []
                unmatched_pats = set(pats)
                all_pats = frozenset(pats)
                get_all_pubs = False
                pub_prefs = set()
                # Gather the publishers whose catalogs will be needed.
                for pat in pats:
                        try:
                                p_obj = fmri.MatchingPkgFmri(pat)
                        except fmri.IllegalMatchingFmri as e:
                                errors.append(e)
                                continue
                        pub_prefix = p_obj.get_publisher()
                        if pub_prefix:
                                pub_prefs.add(pub_prefix)
                        else:
                                get_all_pubs = True
                # Check each publisher for matches to our patterns.
                for p in xport_cfg.gen_publishers():
                        if not get_all_pubs and p.prefix not in pub_prefs:
                                continue
                        cat = fetch_catalog(p, xport, temp_root)
                        ms, tmp1, u = cat.get_matching_fmris(pats)
                        # Find which patterns matched.
                        matched_pats = all_pats - u
                        # Remove those patterns from the unmatched set.
                        unmatched_pats -= matched_pats
                        for v_list in ms.values():
                                concrete_fmris.extend([(v, p) for v in v_list])
                if unmatched_pats:
                        raise api_errors.PackageMatchErrors(
                            unmatched_fmris=unmatched_pats)

                for pfmri, src_pub in sorted(set(concrete_fmris)):
                        try:
                                # Get the existing manifest for the package to
                                # be signed.
                                m_str = xport.get_manifest(pfmri,
                                    content_only=True, pub=src_pub)
                                m = manifest.Manifest()
                                m.set_content(content=m_str)

                                # Construct the base signature action.
                                attrs = { "algorithm": sig_alg }
                                a = actions.signature.SignatureAction(cert_path,
                                    **attrs)
                                a.hash = cert_path

                                # Add the action to the manifest to be signed
                                # since the action signs itself.
                                m.add_action(a, misc.EmptyI)

                                # Set the signature value and certificate
                                # information for the signature action.
                                a.set_signature(m.gen_actions(),
                                    key_path=key_path, chain_paths=chain_certs,
                                    chash_dir=chash_dir)

                                # The hash of 'a' is currently a path, we need
                                # to find the hash of that file to allow
                                # comparison to existing signatures.
                                hsh = None
                                if cert_path:
                                        # Action identity still uses the 'hash'
                                        # member of the action, so we need to
                                        # stay with the sha1 hash.
                                        hsh, _dummy = \
                                            misc.get_data_digest(cert_path,
                                            hash_func=hashlib.sha1)

                                # Check whether the signature about to be added
                                # is identical, or almost identical, to existing
                                # signatures on the package.  Because 'a' has
                                # already been added to the manifest, it is
                                # generated by gen_actions_by_type, so the cnt
                                # must be 2 or higher to be an issue.
                                cnt = 0
                                almost_identical = False
                                for a2 in m.gen_actions_by_type("signature"):
                                        try:
                                                if a.identical(a2, hsh):
                                                        cnt += 1
                                        except api_errors.AlmostIdentical as e:
                                                e.pkg = pfmri
                                                errors.append(e)
                                                almost_identical = True
                                if almost_identical:
                                        continue
                                if cnt == 2:
                                        continue
                                elif cnt > 2:
                                        raise api_errors.DuplicateSignaturesAlreadyExist(pfmri)
                                assert cnt == 1, "Cnt was:{0}".format(cnt)

                                if not dry_run:
                                        # Append the finished signature action
                                        # to the published manifest.
                                        t = trans.Transaction(repo_uri,
                                            pkg_name=str(pfmri), xport=xport,
                                            pub=src_pub)
                                        try:
                                                t.append()
                                                t.add(a)
                                                for c in chain_certs:
                                                        t.add_file(c)
                                                t.close(add_to_catalog=
                                                    add_to_catalog)
                                        except:
                                                if t.trans_id:
                                                        t.close(abandon=True)
                                                raise
                                msg(_("Signed {0}").format(pfmri.get_fmri(
                                    include_build=False)))
                                successful_publish = True
                        except (api_errors.ApiException, fmri.FmriError,
                            trans.TransactionError) as e:
                                errors.append(e)
                if errors:
                        error("\n".join([str(e) for e in errors]))
                        if successful_publish:
                                return EXIT_PARTIAL
                        else:
                                return EXIT_OOPS
                return EXIT_OK
        except api_errors.ApiException as e:
                error(e)
                return EXIT_OOPS
        finally:
                shutil.rmtree(temp_root)

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":
        try:
                __ret = main_func()
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = EXIT_OOPS
        except SystemExit as _e:
                raise _e
        except:
                traceback.print_exc()
                error(misc.get_traceback_message())
                __ret = 99
        sys.exit(__ret)
