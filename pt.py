#!/usr/bin/env python
#
# Copyright (C) 2015 The Yudatun Open Source Project
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#

import sys
import re

from types import *

class Bug(object):

  def blue(self, msg):
    print "\033[1;34m%s\033[0m" % msg

  def green(self, msg):
    print "\033[1;32m%s\033[0m" % msg

  def ok(self, msg):
    self.green(msg)

  def info(self, msg):
    print "\033[1;31m"
    print "INFO: %s" % msg
    print "\033[0m"

  def warn(self, msg):
    print "\033[1;31m"
    print "WARNING: %s" % msg
    print "\033[0m"
    sys.exit(1)

  def error(self, msg):
    print "\033[1;31m"
    print "ERROR: %s" % msg
    print "\033[0m"
    sys.exit(1)

BUG = Bug()

########################################

BYTES_PER_SECTOR = 512

def str2bool(s):
  return s.lower() in ("True", "true")

def kb2sectors(kb):
  return int(kb * 1024 / BYTES_PER_SECTOR)

def sectors_till_next_bulk(lba, kb_per_bulk):
  sectors_per_bulk = kb2sectors(kb_per_bulk)
  if sectors_per_bulk > 0 and \
     (lba % sectors_per_bulk) > 0:
    return sectors_per_bulk - (lba % sectors_per_bulk)

  return 0

########################################

class Instructions(object):

  def __init__(self):
    self.WRITE_PROTECT_BULK_SIZE_IN_KB = 65536  # 64MB
    self.WRITE_PROTECT_GPT             = False
    self.SECTOR_SIZE_IN_BYTES          = 512
    self.AUTO_GROW_LAST_PARTITION      = False
    self.DISK_SIGNATURE                = 0x00000000

  def trim_spaces(self, text):
    # Trim the left of '=' spaces
    tmp = re.sub(r"(\t| )+=", "=", text)
    # Trim the right of '=' spaces
    tmp = re.sub(r"=(\t| )+", "=", tmp)
    return tmp

  def text2list(self, text):
    tmp = re.sub(r"\s+|\n", " ", text)  # Trim '\n'
    tmp = re.sub(r"^\s+", "", tmp)      # Trim '\t\n\r\f\v'
    tmp = re.sub(r"\s+$", "", tmp)
    return tmp.split(' ')

  def text2expr(self, text):
    _list = self.text2list(self.trim_spaces(text))
    for l in _list:
      tmp = l.split('=')
      if len(tmp) == 2:
        key   = tmp[0].strip()
        value = tmp[1].strip()
        if key == 'WRITE_PROTECT_BULK_SIZE_IN_KB':
          if str.isdigit(value):
            self.WRITE_PROTECT_BULK_SIZE_IN_KB = int(value)
        elif key == 'WRITE_PROTECT_GPT':
          self.WRITE_PROTECT_GPT = str2bool(value)
        elif key == 'SECTOR_SIZE_IN_BYTES':
          if str.isdigit(value):
            self.SECTOR_SIZE_IN_BYTES = int(value)
            BYTES_PER_SECTOR = self.SECTOR_SIZE_IN_BYTES
        elif key == 'AUTO_GROW_LAST_PARTITION':
          self.AUTO_GROW_LAST_PARTITION = str2bool(value)
        elif key == 'DISK_SIGNATURE':
          self.DISK_SIGNATURE = int(value, 16)
        else:
          BUG.warn("Invalidate key (%s)" % key)
      else:
        BUG.warn("Invalidate expression (%s)" % l)

INSTRUCTIONS = Instructions()

########################################

class WriteProtectChunk(object):

  def __init__(self):
    self.start_sector = 0
    self.end_sector   = 0
    self.num_sectors  = 0
    self.start_bulk   = 0
    self.num_bulk     = 0

########################################

class Partitions(object):

  GPT_TYPE = "gpt"
  MBR_TYPE = "mbr"

  def __init__(self):
    self._type         = None
    self.part_list     = []
    self.wp_chunk_list = []
    self.wp_chunk_list.append(WriteProtectChunk())

  def add_part(self, part):
    self.part_list.append(part)

  def update_wp_chunk_list(self, start, sectors, sectors_per_bulk):
    start_sector = start - 1
    end_sector   = start + sectors - 1
    last_wp_chunk = self.wp_chunk_list[-1]
    if start_sector <= last_wp_chunk.end_sector:
      # Current Write Protect Chunk already covers the start of this partition
      # which needs to write protection. Bug current Write Protect Chunk
      # is not big enough.
      while end_sector > last_wp_chunk.end_sector:
        last_wp_chunk.end_sector  += sectors_per_bulk
        last_wp_chunk.num_sectors += sectors_per_bulk
      last_wp_chunk.num_bulk = last_wp_chunk.num_sectors / sectors_per_bulk
    else:
      # A new Write Protect Chunk needed.
      new_wp_chunk = WriteProtectChunk()
      new_wp_chunk.start_sector = start
      new_wp_chunk.end_sector   = start + sectors_per_bulk - 1
      new_wp_chunk.num_sectors  = sectors_per_bulk
      while end_sector > new_wp_chunk.end_sector:
        new_wp_chunk.end_sector  += sectors_per_bulk
        new_wp_chunk.num_sectors += sectors_per_bulk
      new_wp_chunk.start_bulk = new_wp_chunk.start_sector / sectors_per_bulk
      new_wp_chunk.num_bulk   = new_wp_chunk.num_sectors / sectors_per_bulk
      self.wp_chunk_list.append(new_wp_chunk)

PARTITIONS = Partitions()

########################################

class Partition(object):

  GUID_RE_1 = "0x([a-fA-F\d]{32})"
  GUID_RE_2 = "([a-fA-F\d]{8})-([a-fA-F\d]{4})-"                \
              "([a-fA-F\d]{4})-([a-fA-F\d]{2})([a-fA-F\d]{2})-" \
              "([a-fA-F\d]{2})([a-fA-F\d]{2})([a-fA-F\d]{2})"   \
              "([a-fA-F\d]{2})([a-fA-F\d]{2})([a-fA-F\d]{2})"

  TYPE_RE   = "^(0x)?([a-fA-F\d][a-fA-F\d]?)$"

  PARTITION_BASIC_DATA_GUID = 0xC79926B7B668C0874433B9E5EBD0A0A2

  def __init__(self):
    self.is_gpt    = False
    self.is_mbr    = False

    # COMMON TAG
    self.label           = ""
    self.first_lba_in_kb = 0  # KB (MBR Only TAG)
    self.size_in_kb      = 0  # KB
    self.size_in_sec     = 0  # sector
    self._type           = ""
    self.filename        = ""
    self.sparse          = ""

    self.uniqueguid    = "" # GPT Only TAG
    # MBR Attributes

    self.bootable      = False
    # GPT Attributes
    self.readonly      = False
    self.hidden        = False
    self.dontautomount = False
    self.system        = False

  def is_validate_GUID(self, GUID):
    if type(GUID) is not str:
      GUID = str(GUID)

    m = re.search(self.GUID_RE_1, GUID)
    if (type(m) is not NoneType) and (len(GUID) == 32):
      return True
    m = re.search(self.GUID_RE_2, GUID)
    if (type(m) is not NoneType) and (len(GUID) == 36):
      return True

    return False

  def is_validate_TYPE(self, TYPE):
    if type(TYPE) is int:
      if TYPE >= 0 and TYPE <= 255:
        return True

    if type(TYPE) is not str:
      TYPE = str(TYPE)

    m = re.search(self.TYPE_RE, TYPE)
    if type(m) is not NoneType:
      return True

    return False

  def validate_GUID(self, GUID):
    if type(GUID) is not str:
      GUID = str(GUID)

    m = re.search(self.GUID_RE_1, GUID)
    if type(m) is not NoneType:
      tmp = int(m.group(1), 16)
      return tmp

    m = re.search(self.GUID_RE_2, GUID)
    if type(m) is not NoneType:
      tmp  = int(m.group(4),  16) << 64
      tmp |= int(m.group(3),  16) << 48
      tmp |= int(m.group(2),  16) << 32
      tmp |= int(m.group(1),  16)

      tmp |= int(m.group(8),  16) << 96
      tmp |= int(m.group(7),  16) << 88
      tmp |= int(m.group(6),  16) << 80
      tmp |= int(m.group(5),  16) << 72

      tmp |= int(m.group(11), 16) << 120
      tmp |= int(m.group(10), 16) << 112
      tmp |= int(m.group(9),  16) << 104
      return tmp
    else:
      return self.PARTITION_BASIC_DATA_GUID

  def validate_TYPE(self, TYPE):
    if type(TYPE) is int:
      if TYPE >= 0 and TYPE <= 255:
        return TYPE

    if type(TYPE) is not str:
      TYPE = str(TYPE)

    m = re.search(self.TYPE_RE, TYPE)
    if type(m) is not NoneType:
      return int(m.group(2), 16)

    BUG.warn("type (%s) is not in the form 0x##." % TYPE)

  def items2expr(self, items):
    for key, value in items:

      if key == 'label':
        self.label = value
      elif key == 'first_lba_in_kb':
        if str.isdigit(value):
          self.first_lba_in_kb = int(value)
      elif key == 'size_in_kb':
        if str.isdigit(value):
          self.size_in_kb = int(value)
        else:
          BUG.warn("Invalid value (%s) for key (%s)" % (value, key))
      elif key == 'type':
        if self.is_validate_GUID(value) is True:
          self.is_gpt = True
          self._type = self.validate_GUID(value)
        elif self.is_validate_TYPE(value) is True:
          self.is_mbr = True
          self._type = self.validate_TYPE(value)
        else:
          BUG.warn("Invalid type (%s)" % value)
      elif key == 'uniqueguid':
        self.uniqueguid = value
      elif key == 'bootable':
        self.bootable = str2bool(value)
      elif key == 'readonly':
        self.readonly = str2bool(value)
      elif key == 'hidden':
        self.hidden = str2bool(value)
      elif key == 'dontautomount':
        self.dontautomount = str2bool(value)
      elif key == 'system':
        self.system = str2bool(value)
      elif key == 'filename':
        self.filename = value
      elif key == 'sparse':
        self.sparse = value
      else:
        BUG.warn("Invalid key (%s)" % key)

    self.size_in_sec = kb2sectors(self.size_in_kb)
