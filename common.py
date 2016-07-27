#!/usr/bin/env python
#
# Copyright (C) 2015 The Yudatun Open Source Project
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#

import os
import getopt
import subprocess
import sys

class Options(object): pass

OPTIONS = Options()

OPTIONS.verbose = False

COMMON_DOCSTRING = """
  -v  (--verbose)
      Show command lines beging executed.

  -h  (--help)
      Display this usage message and exit.
"""

def usage(docstring):
  print docstring.rstrip("\n")
  print COMMON_DOCSTRING

def parseOptions(argv, docstring,
                 extra_opts="", extra_long_opts=(),
                 extra_option_handler=None):
  """Parse the options in argv and return any arguments that aren't
  flags. docstring is the calling module's docstring, to be displayed
  for errors and -h. extra_opts and extra_long_opts are for flags
  defined by the caller, which are processed by passing them to
  extra_option_handler"""

  try:
    opts, args = getopt.getopt(argv, "hv" + extra_opts,
                               ["help", "verbose",] +
                               list(extra_long_opts))
  except getopt.GetoptError, err:
    usage(docstring)
    print "**", str(err), "**"
    sys.exit(2)

  for opt, arg in opts:
    if opt in ("-h", "--help"):
      usage(docstring)
      sys.exit()
    elif opt in ("-v", "--verbose"):
      OPTIONS.verbose = True
    else:
      if extra_option_handler is None or not extra_option_handler(opt, arg):
        assert False, "unknown option \"%s\"" % (opt,)

  return args

def run(args, **kwargs):
  """Create and return a subprocess.Popen object, printing the command
  line on the terminal if -v was specified."""
  if OPTIONS.verbose:
    print "  running: ", " ".join(args)
  return subprocess.Popen(args, **kwargs)

def runCommand(cmd):
  """Echo and run the given command.

  Args:
    cmd: the command represented as a list of strings.
  Returns:
    A tuple of the output and the exit code.
  """
  print "Running: ", " ".join(cmd)
  p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  output, _ = p.communicate()
  print "%s" % (output.tstrip(),)
  return (output, p.returncode)
