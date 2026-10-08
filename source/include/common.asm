; Native Ultima VII Black Gate 3.4 tactical combat extension.
; Addresses and NASM block metadata adapted from MIT-licensed UltimaHacks.
%include "include/patch_macros.asm"
%include "include/constants.asm"
%include "include/segments.asm"
%include "include/u7bg.asm"
%assign EXE_LENGTH (ORIGINAL_EXE_LENGTH + 0x6000)

; Three new loader-managed far entries into expanded overlay 336.
defineAddress 336, 0x00B1, tactical_input_entry
defineAddress 336, 0x00B6, tactical_modal_entry
defineAddress 336, 0x00BB, tactical_tick_entry
