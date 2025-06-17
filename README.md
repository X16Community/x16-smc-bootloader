# Table of Contents

- [Project Description](#project-description)
- [How the Bootloader Works](#how-the-bootloader-works)
    - [Introduction](#introduction)
    - [Bootloader Entry Points](#bootloader-entry-points)
    - [Transmitting the New Firmware](#transmitting-the-new-firmware)
    - [Verifying the new Firmware](#verifying-the-new-firmware)
    - [Fail-Safe](#fail-safe)
- [SMC Memory Map](#smc-memory-map)
- [Building the Project](#building-the-project)
- [Installing the Bootloader](#installing-the-bootloader)
    - [Overview](#overview)
    - [In-System Update of the Bootloader](#in-system-update-of-the-bootloader)
    - [Programming the SMC with an External Programmer](#programming-the-smc-with-an-external-programmer)
    
- [I2C API](#i2c-api)
    - [Command 0x80 = Transmit (master write)](#command-0x80--transmit-master-write)
    - [Command 0x81 = Commit (master read)](#command-0x81--commit-master-read)
    - [Command 0x82 = Reboot (master write)](#command-0x82--reboot-master-write)
    - [Command 0x83 = Get bootloader version (master read)](#command-0x83--get-bootloader-version-master-read)
    - [Command 0x84 = Rewind target address (master write)](#command-0x84--rewind-target-address-master-write)
    - [Command 0x85 = Read flash memory](#command-0x85--read-flash-memory)

# Project Description

This is a custom bootloader for the Commander X16 ATtiny861 based System Management Controller (SMC).

The bootloader makes it possible to update the SMC firmware from the Commander X16 without using an external programmer.

The firmware is stored at the beginning of the flash memory (byte address 0x0000-0x1dff) and provides an interface to the PS/2 keyboard
and mouse. It also handles the phsysical push buttons and the LEDs of the system.

The bootloader is a separate program that is stored at the end of the flash memory (byte address 0x1e00-0x1fff).

All addresses mentioned in this document are byte addresses, unless otherwise specified.


# How the Bootloader Works

## Introduction

For detailed information on how to update the SMC firmware, go to the [SMC Update Guide](https://github.com/X16Community/x16-smc/blob/main/doc/update-guide.md).

This section describes the inner workings of the bootloader. The information is of most interest to those who write tools that use the bootloader.

## Bootloader Entry Points

The bootloader has two entry points: the main entry point at address 0x1e00, and the start update entry point at address 0x1e02.

### Main Entry Point (0x1e00)

As soon as you connect the system to mains power, the SMC executes its reset procedure. That ends by calling the reset vector at address 0x0000. 

Before bootloader v3 the reset vector pointed directly to firmware code.

From bootloader v3 the reset vector jumps to the bootloader main entry point at address 0x1e00. If, however, an older version of the bootloader
was installed, and the bootloader was upgraded to v3 using an in-system upgrade tool, the reset vector at address 0x0000 is not set to
the main entry point until you also update the firmware. In that case the reset vector continues to point to firmware code, and the [fail-safe](#fail-safe) introduced in
bootloader v3 is not enabled.

The main entry point does the following when called.

First it checks if the reset button is being pressed.

If the button is pressed, the computer is turned on, and the SMC update procedure is started. This method of starting the bootloader, holding down the reset button while
connecting the system to power, works in most situations even if the firmware has been bricked. Read more about that
under [fail-safe](#fail-safe). The update program running on the Commander X16 must be loaded and started without keyboard or mouse support, 
which are not available while the bootloader is running. One option is to store the update program as an autostarting program on the SD card.

If the reset button is not pressed, execution continues with the firmware's own reset vector. That vector is moved to the EE_RDY (EEPROM Ready) vector
at address 0x0012 when updating the firmware using the bootloader. The EE_RDY vector is not used by standard Arduino libraries, and is
used for the same purpose by Optiboot. The solution prevents using the EEPROM Ready interrupt in firmware code.

Downgrading the bootloader from v3 requires special care if done with an in-system tool. You must ensure that the fail-safe is uninstalled by
pointing the reset vector directly to firmware code. This can be done by first updating the bootloader and then the firmware without resetting the
SMC in between. Downgrading the bootloader using in-system tools is a riskful operation that should be avoided unless you have access to an
external programmer that can be used to unbrick the SMC.

### Start Update Entry Point (0x1e02)

The start update entry point is to be called while the computer is running. The update
procedure is started immediately after calling this entry point.

A program running on the X16 cannot directly call the start update entry point. To make the SMC jump to this entry point, 
the X16 program have to send I2C command 0x8f (start bootloader).

## Transmitting the New Firmware

During the update procedure, the new firmware is sent to the bootloader over I2C. The bootloader is responsible
for checking the integrity of the received data, and for writing it to the flash memory.

The transmission is divided into packets. Each packet consists of eight firmware bytes and one checksum byte. The
checksum is the two's complement of the sum of the previous bytes in the packet. I2C command offset 0x80 is used
to transmit each byte of a packet.

After all nine bytes of a packet have been transmitted, the packet is committed with I2C command offset 0x81.

Note that the SMC can only update the flash memory in whole pages of 64 bytes. The received
bytes are buffered until there is a full page that can be written to flash memory.

When writing the first 64 bytes to flash memory, the bootloader takes these special actions:

- The firmware area is erased starting from the end.
- The firmware's reset vector is moved to EE_RDY (address 0x0012).
- The reset vector (address 0x0000) is replaced by a jump to the bootloader main entry point

The update procedure continues by transmitting and committing packets until the whole firmware has been
received by the bootloader.

Finally, the update program must use I2C command offset 0x82 (reboot). This will
write any remaining buffered data to flash memory. The SMC is then reset, which turns off the computer.

### Example

This is a simple example illustrating the communication between the Commander X16 and the bootloader
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
...|
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

## Verifying the New Firmware

It is possible to verify the new firmware before the reboot command. The update program
can rewind the target address to 0x0000 with I2C command offset 0x84, and read one byte
at a time from the flash memory using I2C command offset 0x85.

The SMC flash memory can only be updated one page at a time. A page is 64 bytes.
In order to successfully verify the the update, the update program must ensure
that the last page is filled before starting the verify operation. 
If necessary, the update program must send blank data to fill the last page. 
If this is not done, the bootloader will write the last page to flash memory not 
until the reboot command.

## Fail-Safe

The bootloader is designed to be fail-safe. In many
cases the update procedure can be started even if 
the firmware is bricked:

- The update procedure is interrupted during the firmware erase stage: Firmware
erase starts from the last page. If interrupted during this stage,
the reset vector at address 0x0000 is still unchanged. The update
procedure can be started by holding down reset when connecting the system
to power.

- The update procedure is interrupted after the whole firmware has been erased but
before writing any parts of the new firmware to flash memory: When
erasing the flash memory, all words are set to byte value 0xffff, 
which is interpreted as No Operation (NOP) by the SMC hardware. Execution
starts from the reset vector at 0x0000 and continues until
the first non-NOP instruction at 0x1e00, the bootloader main function.
This makes it possible to start the update procedure in this situation.

- The update procedure is interrupted after writing parts of the new
firmware to flash memory: The first page written to flash memory
holds the reset vector that jumps to the bootloader main function making
it possible to start the update procedure.


# SMC Memory Map

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

- you want to update the bootloader version,
- the SMC is replaced by a new chip, or
- the SMC has been corrupted and needs to be reinstalled.

## In-System Update of the Bootloader

If you already have a functioning system, it is possible to do an
in-system update of the bootloader without an external programmer.

Instructions on how to do that are found [here](https://github.com/X16Community/x16-smc/blob/main/doc/smc-bootloader-tools.md).

## Programming the SMC with an External Programmer

It is always possible to install the bootloader using an External Programmer. Usually
you install a packet that contains both the SMC firmware and the bootloader. Such packets are
available from the [X16-SMC release page](https://github.com/X16Community/x16-smc/releases).

### Fuse Settings

The bootloader and the SMC firmware depend on several ATtiny fuse settings as set out below.

The recommended low fuse value is 0xF1. This will run the SMC at 16 MHz.

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

## Command 0x81 = Commit (master read)

After a data packet of 9 bytes has been transmitted it must be committed with this command. 

The first commit will target flash memory address 0x0000. The target address is moved forward 8 bytes on each successful commit.

The command returns 1 byte. The possible return values are:

Value | Description
------|-------------
1     | OK
2     | Error, packet size not 9
3     | Checksum error
4     | Reserved
5     | Error, overwriting bootloader section

The firmware flash memory area is erased during the 8th successful commit, just before writing the first 64-byte page to flash.

## Command 0x82 = Reboot (master write)

The reboot command must always be called after the last packet
has been committed. If not, the SMC may be left in an inoperable
state.

The command first writes any buffered data to flash.

The bootloader then resets the SMC. The SMC reset shuts down the computer. It
can be restarted by pressing the power button. It is not necessary to power cycle the system
after an update.

## Command 0x83 = Get bootloader version (master read)

This command returns the bootloader version.

Available since bootloader v3.

## Command 0x84 = Rewind target address (master write)

Rewinds the target address to 0.

Available since bootloader v3.

## Command 0x85 = Read flash memory

Reads one byte of flash memory at the current target address.

The target address is post-incremented one byte.

This function is primarily intended to be used for verifying the
content of the flash memory after an update.

Available since bootloader v3.

