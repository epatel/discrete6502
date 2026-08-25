// A memory-mapped console for the 6502: characters out to a log, characters in
// from a text field.
//
// Three addresses, chosen to keep $3F00 compatible with the character-out port
// the `general` firmware and its demo program already used:
//
//   $3F00  write  a character the CPU is printing. Goes to the log.
//   $3F01  read   the character waiting for the CPU, or 0 if none.
//          write  ACKNOWLEDGE -- discards it, and the next one appears.
//   $3F02  read   status: bit0 = a character is waiting, bit1 = output has room.
//
// The read at $3F01 is deliberately NON-DESTRUCTIVE, and acknowledging is a
// separate write. Consume-on-read is the more usual design, but it punishes
// perfectly ordinary 6502 code: `LDA $3F01` then `CMP $3F01` reads twice and
// would silently eat a character. Here you read as often as you like and say
// when you are done with it.
//
// A minimal input loop is therefore:
//
//         LDA $3F01       ; character waiting?
//         BEQ wait        ; no, keep looking
//         PHA
//         STA $3F01       ; acknowledge (any value); next one appears
//         PLA             ; ...and get on with it
//
// OFF BY DEFAULT, and that is not timidity. This board decodes 14 address bits,
// so every address is inside the 16 KB window, and Klaus Dormann's functional
// test checksums RAM from its data segment up to $3FFF with `ram_top = $40`.
// Intercepting an address means the write never reaches memory, the readback
// differs, and the suite fails a RAM-integrity check that has nothing to do
// with the CPU. Enable the console for your own programs; leave it off for the
// acceptance suite.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define CONSOLE_OUT_ADDR 0x3F00u
#define CONSOLE_IN_ADDR 0x3F01u
#define CONSOLE_STATUS_ADDR 0x3F02u

#define CONSOLE_STATUS_IN_READY 0x01u
#define CONSOLE_STATUS_OUT_ROOM 0x02u

void console_enable(bool on);
bool console_enabled(void);
void console_reset(void);  // drops both queues

// Matches bus_io_fn. Hand it to bus_set_io(), or call it from your own hook.
// Returns true when it handled the access, so memory is not touched.
bool console_io(uint16_t addr, bool is_write, uint8_t *data);

// ---- the host side --------------------------------------------------------
//
// These are called from the OTHER core in the wifi firmware. Each ring has one
// producer and one consumer, and each index is written by exactly one side, so
// no lock is needed -- which matters, because the CPU side runs inside the
// clock loop of a dynamic CPU where a stall is a correctness bug.

// Drain what the CPU has printed. Returns the number of bytes written, and NUL
// terminates when there is room.
uint32_t console_take_output(char *buf, uint32_t cap);

// Queue text for the CPU to read. Returns how many characters were accepted;
// short of strlen(s) means the input ring filled up.
uint32_t console_push_input(const char *s);

uint32_t console_input_pending(void);
uint32_t console_output_pending(void);

// Total characters the CPU has printed since reset, for a UI that wants to show
// activity without draining the ring.
uint32_t console_output_total(void);
