#!/usr/bin/env python
#
# Copyright (C) 2015 The Yudatun Open Source Project
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#

import pt

import xml.etree.ElementTree as ET

INSTRUCTIONS = pt.INSTRUCTIONS
PARTITIONS   = pt.PARTITIONS
BUG          = pt.BUG

BYTES_PER_SECTOR = pt.BYTES_PER_SECTOR

class Parser(object):

  def __init__(self): pass

  def xml2object(self, xml):
    config_count = 0
    instruct_count = 0
    phy_part_count = 0

    root     = ET.parse(xml)
    iterator = root.getiterator()

    for e in iterator:
      if e.tag == "configuration":
        config_count += 1
      elif e.tag == "parser_instructions":
        instruct_count += 1
        INSTRUCTIONS.text2expr(e.text)
      elif e.tag == "physical_partition":
        phy_part_count += 1
      elif e.tag == "partition":
        if e.keys():
          part = pt.Partition()
          part.items2expr(e.items())
          if part.is_gpt is True and part.is_mbr is False:
            PARTITIONS._type = PARTITIONS.GPT_TYPE
          elif part.is_gpt is False and part.is_mbr is True:
            PARTITIONS._type = PARTITIONS.MBR_TYPE
          else:
            BUG.error("Cannot defined the type of partition table.")

          # Now add this Partition object to PARTITIONS unless it's the
          # label EXT, which is a left over legacy tag
          if part.label != 'EXT':
            PARTITIONS.add_part(part)
          else:
            BUG.error("Invalidate label (EXT) for tag (partition).")
        else:
          BUG.info("Empty keys for tag (partition).")
      else:
        BUG.error("Invalidate tag (%s)." % e.tag)

      if config_count > 1 or instruct_count > 1 or phy_part_count > 1:
        BUG.error("Multiple defined tag (%s)." % e.tag)

    if len(PARTITIONS.part_list) == 0:
      BUG.error("Empty tag (physical_partition) was detected.")

    if (PARTITIONS._type is PARTITIONS.GPT_TYPE) and \
       (INSTRUCTIONS.WRITE_PROTECT_GPT is True) and \
       (INSTRUCTIONS.WRITE_PROTECT_BULK_SIZE_IN_KB != 0):
      sectors_per_bulk = pt.kb2sectors(INSTRUCTIONS.WRITE_PROTECT_BULK_SIZE_IN_KB)
      first_chunk = PARTITIONS.wp_chunk_list[0]
      first_chunk.start_sector = 0
      first_chunk.end_sector   = sectors_per_bulk - 1
      first_chunk.num_sectors  = sectors_per_bulk
      first_chunk.start_bulk   = first_chunk.start_sector / sectors_per_bulk
      first_chunk.num_bulk     = first_chunk.num_sectors / sectors_per_bulk


PARSER = Parser()
