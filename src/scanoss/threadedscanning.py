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
import os
import sys
import threading
import queue
import time

from typing import Dict, List
from dataclasses import dataclass
from progress.bar import Bar

from .scanossapi import ScanossApi

WFP_FILE_START = "file="
MAX_ALLOWED_THREADS = 30

@dataclass
class ThreadedScanning(object):
    """
    Threaded class for running Scanning in parallel (from a queue)
    WFP scan requests are loaded into the input queue.
    Multiple threads pull messages off this queue, process the request and put the results into an output queue
    """
    inputs: queue.Queue = queue.Queue()
    output: queue.Queue = queue.Queue()
    bar: Bar = None

    def __init__(self, scanapi :ScanossApi, debug: bool = False, trace: bool = False, quiet: bool = False,
                 nb_threads: int = 5
                 ) -> None:
        """
        Initialise the ThreadedScanning class
        :param scanapi: SCANOSS API to send scan requests to
        :param debug: enable debug (default False)
        :param trace: enable trace (default False)
        :param quiet: enable quiet mode (default False)
        :param nb_threads: Number of thread to run (default 5)
        """
        self.scanapi = scanapi
        self.debug = debug
        self.trace = trace
        self.quiet = quiet
        self.nb_threads = nb_threads
        self._isatty = sys.stderr.isatty()
        self._bar_count = 0
        self._errors = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._threads = []
        if nb_threads > MAX_ALLOWED_THREADS:
            self.print_msg(f'Warning: Requested threads too large: {nb_threads}. Reducing to {MAX_ALLOWED_THREADS}')
            self.nb_threads = MAX_ALLOWED_THREADS

    @staticmethod
    def print_stderr(*args, **kwargs):
        """
        Print the given message to STDERR
        """
        print(*args, file=sys.stderr, **kwargs)

    @staticmethod
    def __count_files_in_wfp(wfp: str):
        """
        Count the number of files in the WFP that need to be processed
        :param wfp: WFP string
        :return: number of files in the WFP
        """
        count = 0
        if wfp:
            for line in wfp.split('\n'):
                if WFP_FILE_START in line:
                    count += 1
        return count

    def print_msg(self, *args, **kwargs):
        """
        Print message if quite mode is not enabled
        """
        if not self.quiet:
            self.print_stderr(*args, **kwargs)

    def print_debug(self, *args, **kwargs):
        """
        Print debug message if enabled
        """
        if self.debug:
            self.print_stderr(*args, **kwargs)

    def print_trace(self, *args, **kwargs):
        """
        Print trace message if enabled
        """
        if self.trace:
            self.print_stderr(*args, **kwargs)

    def create_bar(self, file_count: int):
        if not self.quiet and self._isatty and not self.bar:
            self.bar = Bar('Scanning', max=file_count)
            self.bar.next(self._bar_count)

    def complete_bar(self):
        if self.bar:
            self.bar.finish()

    def set_bar(self, bar: Bar) -> None:
        """
        Set the Progress Bar to display progress while scanning
        :param bar: Progress Bar object
        """
        self.bar = bar

    def update_bar(self, amount: int = 0, create: bool = False, file_count: int = 0) -> None:
        """
        Update the Progress Bar progress
        :param amount: amount of progress to update
        """
        try:
            self._lock.acquire()
            try:
                if create and not self.bar:
                    self.create_bar(file_count)
                elif self.bar:
                    self.bar.next(amount)
                self._bar_count += amount
            finally:
                self._lock.release()
        except Exception as e:
            self.print_debug(f'Warning: Update status bar lock failed: {e}. Ignoring.')

    def queue_add(self, wfp: str) -> None:
        """
        Add requests to the queue
        :param wfp: WFP to add to queue
        """
        self.inputs.put(wfp)

    def get_queue_size(self) -> int:
        return self.inputs.qsize()

    @property
    def responses(self) -> List[Dict]:
        """
        Get all responses back from the completed threads
        :return: List of JSON objects
        """
        return list(self.output.queue)

    def run(self, wait: bool = True) -> bool:
        """
        Initiate the threads and process all pending requests
        :return: True if successful, False if error encountered
        """
        qsize = self.inputs.qsize()
        if qsize < self.nb_threads:
            self.print_debug(f'Input queue ({qsize}) smaller than requested threads: {self.nb_threads}. '
                             f'Reducing to queue size.')
            self.nb_threads = qsize
        else:
            self.print_debug(f'Starting {self.nb_threads} threads to process {qsize} requests...')
        try:
            for i in range(0, self.nb_threads):
                t = threading.Thread(target=self.worker_post, daemon=True)
                self._threads.append(t)
                t.start()
        except Exception as e:
            self.print_stderr(f'ERROR: Problem running threaded scanning: {e}')
            self._errors = True
        if wait:                    # Wait for all inputs to complete
            self.complete()
        return False if self._errors else True

    def complete(self) -> None:
        """
        Wait for input queue to complete processing and complete the worker threads
        """
        self.inputs.join()
        self._stop_event.set()       # Tell the worker threads to stop
        try:
            for t in self._threads:  # Complete the threads
                t.join(timeout=5)
        except Exception as e:
            self.print_stderr(f'WARNING: Issue encountered terminating scanning worker threads: {e}')

    def worker_post(self) -> None:
        """
        Take each request and process it
        :return: None
        """
        current_thread = threading.get_ident()
        self.print_trace(f'Starting worker {current_thread}...')
        while not self._stop_event.is_set():
            wfp = None
            if not self.inputs.empty():          # Only try to get a message if there is one on the queue
                try:
                    wfp = self.inputs.get(timeout=5)
                    self.print_trace(f'Processing input request ({current_thread})...')
                    count = self.__count_files_in_wfp(wfp)
                    resp = self.scanapi.scan(wfp, scan_id=current_thread)
                    if resp:
                        self.output.put(resp)  # Store the output response to later collection
                    self.update_bar(count)
                    self.inputs.task_done()
                    self.print_trace(f'Request complete ({current_thread}).')
                except queue.Empty as e:
                    self.print_stderr(f'No message available to process ({current_thread}). Checking again...')
                except Exception as e:
                    ThreadedScanning.print_stderr(f'ERROR: Problem encountered running scan: {e}')
                    self._errors = True
                    if wfp:
                        self.inputs.task_done()  # If there was a WFP being processed, remove it from the queue
            else:
                time.sleep(1)  # Sleep while waiting for the queue depth to build up
        self.print_trace(f'Thread complete ({current_thread}).')

#
# End of ThreadedScanning Class
#