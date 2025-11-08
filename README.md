# Table of Contents

- [Project Description](#project-description)
- [Update Procedure](#update-procedure)
    - [Overview](#overview)
    - [Enable Firmware Update Mode](#enable-firmware-update-mode)
    - [Send Data Packets](#send-data-packets)
    - [Commit Data Packets](#commit-data-packets)
    - [Reboot](#reboot)
    - [Example](#example)
- [Fail-Safe (Bootloader v3)](#fail-safe-bootloader-v3)
- [Verifying the New Firmware](#verifying-the-new-firmware)
- [SMC Memory Map](#smc-memory-map)
- [Building the Project](#building-the-project)
- [Installing the Bootloader](#installing-the-bootloader)
    - [Overview](#overview-1)
    - [Updating the Bootloader from the Commander X16](#updating-the-bootloader-from-the-commander-x16)
    - [Programming the SMC with an External Programmer](#programming-the-smc-with-an-external-programmer)
- [I2C API](#i2c-api)
    - [Command 0x80 = Transmit (master write)](#command-0x80--transmit-master-write)
    - [Command 0x81 = Commit (master read)](#command-0x81--commit-master-read)
    - [Command 0x82 = Reboot (master write)](#command-0x82--reboot-master-write)
    - [Command 0x83 = Get bootloader version (master read)](#command-0x83--get-bootloader-version-master-read)
    - [Command 0x84 = Rewind target address (master write)](#command-0x84--rewind-target-address-master-write)
    - [Command 0x85 = Read flash memory](#command-0x85--read-flash-memory)

# Project Description

The bootloader for the Commander X16 System Management Controller (SMC) enables users to update
the SMC firmware directly from the computer without an external programmer.

The SMC firmware handles power control, keyboard and mouse input, and LED states.

The bootloader is a separate program stored at the end of the SMC flash memory.

This document describes the inner workings of the bootloader, which is of most interest
to those who make tools that use the bootloader.

For detailed information on how to update the SMC firmware, 
check out the [SMC Update Guide](https://github.com/X16Community/x16-smc/blob/main/doc/update-guide.md).

All addresses mentioned in this document are byte addresses, unless otherwise specified.


## Update Procedure

### Overview

Updating the SMC firmware involves the following steps:

1. Enable the bootloader's firmware update mode.

2. Send a data packet containing new firmware.

3. Commit the data packet.

4. Repeat steps 2 and 3 until all of the firmware has been transmitted.

5. Send the reboot command to finish the update.


### Enable Firmware Update Mode

There are two ways to enable the bootloader's firmware update mode.

1. Send I2C command 0x8f while the Commander X16 is running. That
command is part of the SMC firmware (not the bootloader). It will call
the start update entry point at address 0x1e02 if you momentarily press
both the power and reset buttons at the same time within approximately
20 seconds. This method of enabling the update mode is supported 
in all versions of the bootloader.

2. Hold down the reset button as you connect the Commander X16 to
mains power. This will enable the update mode on a system fully upgraded to
bootloader v3. This method of initiating an update is referred to as the 
["fail-safe"](#fail-safe-bootloader-v3) and is handled by the bootloader's 
main entry point at address 0x1e00. 

What happens internally when enabling update mode differs between the
bootloader versions.

Bootloader v1 and v2 write their own vectors to the first 64-byte page
of the SMC flash memory. This is used to link interrupt service handlers
for hardware I2C and, in case of v2, reset. The firmware is in 
a non-working state until the update has finished.

Bootloader v3 doesn't use interrupt vectors for hardware I2C. 
No changes are made to the firmware just by enabling update mode.


### Send Data Packets

The new firmware is transmitted to the bootloader in data packets.
Each packet holds eight bytes of firmware data and one checksum byte,
a total of nine bytes.

The checksum is the two's complement of the sum of the previous bytes
within the packet.

Use I2C command 0x80 (transmit) to send each byte including the checksum.


### Commit Data Packets

After all nine bytes of a packet have been transmitted to the bootloader,
the packet must be committed. This is done with I2C command 0x81 (commit).

The bootloader sends a response code indicating whether the command
was successful or not. If the command failed, it is possible to resend the
the packet and commit it again.

The internal flash address pointer is automatically incremented on each successful commit.

The SMC hardware can only write to the flash memory in full 64-byte pages. The
received data is buffered in RAM until there is a full page that can
be written to flash.

Bootloader v1 and v2 keeps the new firmware for the first 64-byte page in
RAM instead of writing it to flash. As mentioned above, the first page 
holds vectors that are used by these bootloader versions. 
The first page is written to flash at the end of the update procedure.

Bootloader v3 writes each full 64-byte page to flash in the order it's received, 
including the first page. Before writing the first page, bootloader v3 
erases all of the old firmware, starting from the end. When updating the 
first page, the bootloader moves the firmware's reset vector (address 0x0000) 
to the EE_RDY vector (0x0012). The reset vector is changed to point to the 
bootloader's main entry point. This is part of the bootloader's 
[fail-safe](#fail-safe-bootloader-v3) mechanism.


### Reboot

After all of the new firmware has been transmitted and committed, send
I2C command 0x82 (reboot) to finish the update.

The reboot command writes any buffered data to the current
64-byte page.

What happens next differs between the bootloader versions.

- Bootloader v1 writes the first 64-byte page to flash and enters
an infinite loop. You need to power cycle the system to start
the computer after the update.

- Bootloader v2 resets the SMC with the watchdog timer. After
reset, execution starts with the reset vector at address 0x0000. When
enabling update mode, this was set to jump to a function in the
bootloader that writes the first 64-byte page to flash. The bootloader
then jumps to the firmware's real reset vector, which effectively
turns off the computer. There is no need to power cycle the computer.
You may just press the power button to turn it on again.

- The "bad" bootloader v2 enters an infinite loop just before the 
watchdog reset, which results in the first 64-byte page not 
being updated. You can get past the problem by grounding 
the physical reset pin of the SMC. Instructions on how to do that
are found [here](https://github.com/X16Community/x16-smc/blob/main/doc/update-with-bad-bootloader-v2.md).

- Bootloader v3 resets the SMC with the watchdog timer. The
first 64-byte page was already written to flash when first received.


### Example

This is a simple example of communication between the Commander X16 and the bootloader
during an update.

Cmd | R/W | Data | Comment
----|-----|------|---------------------
0x80 | W  | 0x01 | 1st packet, 1st byte
0x80 | W  | 0x02 | 1st packet, 2nd byte
0x80 | W  | 0x03 | 1st packet, 3rd byte
0x80 | W  | 0x04 | 1st packet, 4th byte
0x80 | W  | 0x05 | 1st packet, 5th byte
0x80 | W  | 0x06 | 1st packet, 6th byte
0x80 | W  | 0x07 | 1st packet, 7th byte
0x80 | W  | 0x08 | 1st packet, 8th byte
0x80 | W  | 0xdc | 1st packet, checksum
0x81 | R  | 0x01 | Commit 1st packet, OK response
...
0x80 | W  | 0x09 | nth packet, 1st byte
0x80 | W  | 0x0a | nth packet, 2nd byte
0x80 | W  | 0x0b | nth packet, 3rd byte
0x80 | W  | 0x0c | nth packet, 4th byte
0x80 | W  | 0x0d | nth packet, 5th byte
0x80 | W  | 0x0e | nth packet, 6th byte
0x80 | W  | 0x0f | nth packet, 7th byte
0x80 | W  | 0x10 | nth packet, 8th byte
0x80 | W  | 0x9c | nth packet, checksum
0x81 | R  | 0x01 | Commit nth packet, OK response
0x82 | W  | Any  | Reboot


## Fail-Safe (Bootloader v3)

Bootloader v3 introduces a fail-safe mechanism that allows entering 
update mode by holding the reset button on power-up, even if the 
main firmware is corrupted.

The fail-safe mechanism requires that you have a system fully upgraded
to bootloader v3. This can be done as follows:

- When updating the SMC with an external programmer, the fail-safe is
enabled if you use a release including bootloader v3.

- When updating the SMC from the Commander X16, you must first update
the bootloader to v3 and then you must also update the firmware. The
fail-safe mechanism is not enabled if you only update the bootloader.

Go to the [SMC Update Guide](https://github.com/X16Community/x16-smc/blob/main/doc/update-guide.md) 
for further instructions.

When the fail-safe is enabled, the reset vector (address 0x0000) jumps to
the bootloader's main entry point (address 0x1e00). The reset vector is
called every time the SMC hardware is reset, for instance when
you connect the Commander X16 to mains power.

The main entry point checks if the reset button is being pressed. If
so it enables the firmware update mode. If the button is not pressed
it jumps to the firmware's original reset vector that is moved
to the EE_RDY vector (address 0x0012) during an update with bootloader v3.

The main entry point is accessible in most cases even if the firmware
has been corrupted:

- If the update procedure is interrupted during the firmware erase stage: Firmware
erase starts from the last page. If interrupted during this stage,
the reset vector at address 0x0000 is still unchanged and will jump to
the bootloader's main entry point at address 0x1e00.

- If the update procedure is interrupted after the entire firmware has been erased but
before writing any part of the new firmware to flash memory: When
erasing the flash memory, all words are set to byte value 0xffff, 
which is interpreted as No Operation (NOP) by the SMC hardware. Execution
starts from the reset vector at 0x0000 and continues until
the first non-NOP instruction at address 0x1e00, the bootloader's main entry point.
This makes it possible to start the update procedure in this situation as well.

- If the update procedure is interrupted after writing parts of the new
firmware to flash memory: The first page written to flash memory
holds the reset vector that jumps to the bootloader's main entry point making
it possible to start the update procedure.


## Verifying the New Firmware

From bootloader v3 it is possible to verify the update before reboot.

Before starting to verify, the update program must ensure that the entire firmware has been
written to flash memory. The flash memory can only be updated one 64-byte page
at a time. If the last page was only partially filled, the update program must
transmit and commit blank data to fill the last page completely. That way you may
ensure that all of the firmware has been written to flash memory.

Verification starts by rewinding the target address to 0x0000 with I2C command
0x84. The content of the flash memory may then be read one byte at a time
with I2C command 0x85.


# SMC Memory Map

## Bootloader v1 and v2

| Byte address  | Size        | Description                |
|-------------- |-------------| ---------------------------|
| 0x0000-0x1dff | 7,680 bytes | Firmware area              |
| 0x1e00-0x1fff | 512 bytes   | Bootloader area            |
| 0x1e00        | 2 bytes     | Bootloader version         |
| 0x1e02        | 2 bytes     | Start update entry         |   

## Bootloader v3

| Byte address  | Size        | Description                |
|-------------- |-------------| ---------------------------|
| 0x0000-0x1dff | 7,680 bytes | Firmware area              |
| 0x0000        | 2 bytes     | Reset vector               |
| 0x0012        | 2 bytes     | EE_RDY vector              |
| 0x1e00-0x1fff | 512 bytes   | Bootloader area            |
| 0x1e00        | 2 bytes     | Bootloader main entry      |
| 0x1e02        | 2 bytes     | Start update entry         |
| 0x1ffe        | 2 bytes     | Bootloader version         |   


# Building the Project

Type ```make``` to build the bootloader.

Build dependencies:

- make

- AVRA assembler https://github.com/Ro5bert/avra

- Python 3

- Python intelhex module, install with ```pip install intelhex```

The bootloader is also automatically built by a GitHub action.

# Installing the Bootloader

## Overview
The SMC bootloader is installed during manufacturing of the Commander X16.

You need to install the bootloader yourself if:

- You want to update the bootloader version
- The SMC has been replaced by a new chip
- The SMC has been corrupted and needs to be reinstalled

## Updating the Bootloader from the Commander X16

If you already have a functioning system, it is possible to update
the bootloader from the Commander X16 without an external programmer.

Instructions on how to do that are found [here](https://github.com/X16Community/x16-smc/blob/main/doc/smc-bootloader-tools.md).

## Programming the SMC with an External Programmer

It is always possible to install the bootloader using an External Programmer. Usually
you install a packet that contains both the SMC firmware and the bootloader. Such packages are
available from the [X16-SMC release page](https://github.com/X16Community/x16-smc/releases).

### Fuse Settings

The bootloader and the SMC firmware depend on several ATtiny fuse settings as set out below.

The recommended low fuse value is 0xF1. This configures the SMC to run at 16 MHz.

The recommended high fuse value is 0xD4. This enables Brown-out Detection at 4.3V, which is necessary to prevent flash memory corruption when self-programming is enabled. Serial Programming should be enabled (bit 5) and external reset disable should not be selected (bit 7). These settings are necessary for programming the SMC with an external programmer.

Finally, the extended fuse value must be 0xFE to enable self-programming of the flash memory. The bootloader cannot work without this setting.

### Programming with avrdude

Avrdude is the recommended software to use when programming the SMC using an external programmer.

Example 1: Set fuses
```
avrdude -cstk500v1 -Cavrdude.conf -pattiny861 -P<your port> -b19200 -Ulfuse:w:0xF1:m -Uhfuse:w:0xD4:m -Uefuse:w:0xFE:m
```

Example 2: Write to flash
```
avrdude -cstk500v1 -Cavrdude.conf -pattiny861 -P<your port> -b19200 -Uflash:w:build/firmware_with_bootloader.hex:i
```

The -c option selects programmer-id; stk500v1 is for using Arduino UNO as an In-System Programmer. If you have another ISP programmer, you may need to change this value accordingly.

The -p option selects the target device, always attiny861.

The -P option selects port name on the host computer.

The -b option sets transmission baudrate; 19200 is a good value.

The -U option performs a memory programming operation. "-U flash:w:filename:i" writes to flash memory. "-U lfuse:w:0xF1:m" writes the low fuse value.

Please note that some fuse settings may cause the ATtiny861 not to respond. Resetting might require equipment for high voltage programming. Using non-recommended fuse settings may brick the device.

The Arduino IDE also uses avrdude in the background. If you have installed the IDE you may enable verbose output and see what parameters are used by the IDE when it calls avrdude.


# I2C API

## Command 0x80 = Transmit (master write)

The transmit command is used to send a data packet to the bootloader.

A packet consists of 8 bytes to be written to flash and 1 checksum byte.

The checksum is the two's complement of the least significant byte of the sum of the previous bytes in the packet. The least significant byte of the sum of all 9 bytes in a packet will consequently always be 0.

Available since v1.

## Command 0x81 = Commit (master read)

After a data packet of 9 bytes has been transmitted it must be committed with this command. 

The first commit will target flash memory address 0x0000. The target address is advanced 8 bytes on each successful commit.
In bootloader v1 and v2, the first 64-byte page is held in RAM until the end of the update when it's written to flash.

Note that the target address can be rewound to 0x0000 by command 0x84.

The command returns 1 byte. The possible return values are:

Value | Description
------|-------------
1     | OK
2     | Error, packet size not 9
3     | Checksum error
4     | Reserved
5     | Error, overwriting bootloader section

Available since v1.

## Command 0x82 = Reboot (master write)

The reboot command must always be called after the last packet
has been committed. If not, the SMC may be left in an inoperable
state.

The reboot command ensures that any buffered firmware data is written
to the flash memory.

From bootloader v2, the command resets the SMC and the computer can
be restarted by pressing the power button without power cycling the
system as was required in v1.

Available since v1.

## Command 0x83 = Get bootloader version (master read)

This command returns the bootloader version.

Available since v3.

## Command 0x84 = Rewind target address (master write)

Rewinds the target address to 0.

Available since  v3.

## Command 0x85 = Read flash memory

Reads one byte of flash memory at the current target address.

The target address is post-incremented one byte.

This function is primarily intended to be used for verifying the
content of the flash memory after an update.

Available since v3.

