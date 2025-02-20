#!/usr/bin/env python3
"""
 SPDX-License-Identifier: MIT

   Copyright (c) 2021, SCANOSS

   Permission is hereby granted, free of charge, to any person obtaining a copy
   of this software and associated documentation files (the "Software"), to deal
   in the Software without restriction, including without limitation the rights
   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
   copies of the Software, and to permit persons to whom the Software is
   furnished to do so, subject to the following conditions:

   The above copyright notice and this permission notice shall be included in
   all copies or substantial portions of the Software.

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
   THE SOFTWARE.
"""
import argparse
import os
import sys

from .scanner import Scanner
from .winnowing import Winnowing
from . import __version__


def print_stderr(*args, **kwargs):
    """
    Print the given message to STDERR
    """
    print(*args, file=sys.stderr, **kwargs)


def setup_args() -> None:
    """
    Setup all the command line arguments for processing
    """
    parser = argparse.ArgumentParser(description=f'SCANOSS Python CLI. Ver: {__version__}, License: MIT')
    subparsers = parser.add_subparsers(title='Sub Commands', dest='subparser', description='valid subcommands',
                                       help='sub-command help'
                                       )
    # Sub-command: version
    p_ver = subparsers.add_parser('version', aliases=['ver'],
                                   description=f'Version of SCANOSS CLI: {__version__}', help='SCANOSS version')
    p_ver.set_defaults(func=ver)
    # Sub-command: scan
    p_scan = subparsers.add_parser('scan', aliases=['sc'],
                                   description=f'Analyse/scan the given source base: {__version__}',
                                   help='Scan source code')
    p_scan.set_defaults(func=scan)
    p_scan.add_argument('scan_dir', metavar='FILE/DIR', type=str, nargs='?', help='A file or folder to scan')
    p_scan.add_argument('--wfp', '-w',  type=str,
                        help='Scan a WFP File instead of a folder (optional)'
                        )
    p_scan.add_argument('--identify', '-i', type=str, help='Scan and identify components in SBOM file' )
    p_scan.add_argument('--ignore',   '-n', type=str, help='Ignore components specified in the SBOM file' )
    p_scan.add_argument('--output',   '-o', type=str, help='Output result file name (optional - default stdout).' )
    p_scan.add_argument('--format',   '-f', type=str, choices=['plain', 'cyclonedx', 'spdxlite'],
                        help='Result output format (optional - default: plain)'
                        )
    p_scan.add_argument('--threads', '-T', type=int, default=10,
                        help='Number of threads to use while scanning (optional - default 10)'
                        )
    p_scan.add_argument('--flags', '-F', type=int,
                        help='Scanning engine flags (1: disable snippet matching, 2 enable snippet ids, '
                             '4: disable dependencies, 8: disable licenses, 16: disable copyrights,'
                             '32: disable vulnerabilities, 64: disable quality, 128: disable cryptography,'
                             '256: disable best match, 512: Report identified files)'
                        )
    p_scan.add_argument('--skip-snippets', '-S', action='store_true', help='Skip the generation of snippets')
    p_scan.add_argument('--post-size', '-P', type=int, default=64,
                        help='Number of kilobytes to limit the post to while scanning (optional - default 64)'
                        )
    p_scan.add_argument('--timeout', '-M', type=int, default=120,
                        help='Timeout (in seconds) for API communication (optional - default 120)'
                        )
    p_scan.add_argument('--no-wfp-output', action='store_true', help='Skip WFP file generation')
    p_scan.add_argument('--all-extensions', action='store_true', help='Scan all file extensions')
    p_scan.add_argument('--all-folders', action='store_true', help='Scan all folders')
    p_scan.add_argument('--all-hidden', action='store_true', help='Scan all hidden files/folders')

    # Sub-command: fingerprint
    p_wfp = subparsers.add_parser('fingerprint', aliases=['fp', 'wfp'],
                                  description=f'Fingerprint the given source base: {__version__}',
                                  help='Fingerprint source code')
    p_wfp.set_defaults(func=wfp)
    p_wfp.add_argument('scan_dir', metavar='FILE/DIR', type=str, nargs='?',
                       help='A file or folder to scan')
    p_wfp.add_argument('--output', '-o', type=str, help='Output result file name (optional - default stdout).' )

    # Global command options
    for p in [p_scan]:
        p.add_argument('--key', '-k', type=str,
                       help='SCANOSS API Key token (optional - not required for default OSSKB URL)'
                       )
        p.add_argument('--apiurl', type=str,
                       help='SCANOSS API URL (optional - default: https://osskb.org/api/scan/direct)'
                       )
    for p in [p_scan, p_wfp]:
        p.add_argument('--debug', '-d', action='store_true', help='Enable debug messages')
        p.add_argument('--trace', '-t', action='store_true', help='Enable trace messages, including API posts')
        p.add_argument('--quiet', '-q', action='store_true', help='Enable quiet mode')

    args = parser.parse_args()
    if not args.subparser:
        parser.print_help()
        exit(1)
    args.func(parser, args)  # Execute the function associated with the sub-command


def ver(parser, args):
    """
    Run the "ver" sub-command
    Parameters
    ----------
        parser: ArgumentParser
            command line parser object
        args: Namespace
            Parsed arguments
    """
    print(f'Version: {__version__}')


def wfp(parser, args):
    """
    Run the "wfp" sub-command
    Parameters
    ----------
        parser: ArgumentParser
            command line parser object
        args: Namespace
            Parsed arguments
    """
    if not args.scan_dir:
        print_stderr('Please specify a file/folder')
        parser.parse_args([args.subparser, '-h'])
        exit(1)
    scan_output: str = None
    if args.output:
        scan_output = args.output
        open(scan_output, 'w').close()
    scanner = Scanner(debug=args.debug, quiet=args.quiet)

    if not os.path.exists(args.scan_dir):
        print_stderr(f'Error: File or folder specified does not exist: {args.scan_dir}.')
        exit(1)
    if os.path.isdir(args.scan_dir):
        scanner.wfp_folder(args.scan_dir, scan_output)
    elif os.path.isfile(args.scan_dir):
        scanner.wfp_file(args.scan_dir, scan_output)
    else:
        print_stderr(f'Error: Path specified is neither a file or a folder: {args.scan_dir}.')
        exit(1)


def scan(parser, args):
    """
    Run the "scan" sub-command
    Parameters
    ----------
        parser: ArgumentParser
            command line parser object
        args: Namespace
            Parsed arguments
    """
    if not args.scan_dir and not args.wfp:
        print_stderr('Please specify a file/folder or fingerprint (--wfp)')
        parser.parse_args([args.subparser, '-h'])
        exit(1)
    scan_type: str = None
    sbom_path: str = None
    if args.identify:
        sbom_path = args.identify
        scan_type = 'identify'
        if not os.path.exists(sbom_path) or not os.path.isfile(sbom_path):
            print_stderr(f'Specified --identify file does not exist or is not a file: {sbom_path}')
            exit(1)
        if not Scanner.valid_json_file(sbom_path):   # Make sure it's a valid JSON file
            exit(1)
        if args.ignore:
            print_stderr(f'Warning: Specified --identify and --ignore options. Skipping ignore.')
    elif args.ignore:
        sbom_path = args.ignore
        scan_type = 'blacklist'
        if not os.path.exists(sbom_path) or not os.path.isfile(sbom_path):
            print_stderr(f'Specified --ignore file does not exist or is not a file: {sbom_path}')
            exit(1)
        if not Scanner.valid_json_file(sbom_path):   # Make sure it's a valid JSON file
            exit(1)

    scan_output: str = None
    if args.output:
        scan_output = args.output
        open(scan_output, 'w').close()
    output_format = args.format if args.format else 'plain'
    flags = args.flags if args.flags else None
    if args.debug and not args.quiet:
        if args.all_extensions:
            print_stderr("Scanning all file extensions/types...")
        if args.all_folders:
            print_stderr("Scanning all folders...")
        if args.all_hidden:
            print_stderr("Scanning all hidden files/folders...")
        if args.skip_snippets:
            print_stderr("Skipping snippets...")
        if args.post_size != 64:
            print_stderr(f'Changing scanning POST size to: {args.post_size}k...')
        if args.timeout != 120:
            print_stderr(f'Changing scanning POST timeout to: {args.timeout}...')
    elif not args.quiet:
        if args.timeout < 5:
            print_stderr(f'POST timeout (--timeout) too small: {args.timeout}. Reverting to default.')

    if not os.access( os.getcwd(), os.W_OK ):  # Make sure the current directory is writable. If not disable saving WFP
        print_stderr(f'Warning: Current directory is not writable: {os.getcwd()}')
        args.no_wfp_output = True

    scanner = Scanner(debug=args.debug, trace=args.trace, quiet=args.quiet, api_key=args.key, url=args.apiurl,
                      sbom_path=sbom_path, scan_type=scan_type, scan_output=scan_output, output_format=output_format,
                      flags=flags, nb_threads=args.threads, skip_snippets=args.skip_snippets, post_size=args.post_size,
                      timeout=args.timeout, no_wfp_file=args.no_wfp_output, all_extensions=args.all_extensions,
                      all_folders=args.all_folders, hidden_files_folders=args.all_hidden
                      )
    if args.wfp:
        if args.threads > 1:
            scanner.scan_wfp_file_threaded(args.wfp)
        else:
            scanner.scan_wfp_file(args.wfp)
    elif args.scan_dir:
        if not os.path.exists(args.scan_dir):
            print_stderr(f'Error: File or folder specified does not exist: {args.scan_dir}.')
            exit(1)
        if os.path.isdir(args.scan_dir):
            if not scanner.scan_folder(args.scan_dir):
                exit(1)
        elif os.path.isfile(args.scan_dir):
            if not scanner.scan_file(args.scan_dir):
                exit(1)
        else:
            print_stderr(f'Error: Path specified is neither a file or a folder: {args.scan_dir}.')
            exit(1)
    else:
        print_stderr('No action found to process')
        exit(1)


def main():
    """
    Run the ScanOSS CLI
    """
    setup_args()


if __name__ == "__main__":
    main()
