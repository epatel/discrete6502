cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2_w CACHE STRING "Board type")
include(${CMAKE_CURRENT_LIST_DIR}/../common/pico_sdk_import.cmake)
project(discrete6502_general C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()
add_executable(general main.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/bus6502.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/settings.c)
target_include_directories(general PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../common)
target_link_libraries(general pico_stdlib pico_flash)
pico_enable_stdio_usb(general 1)
pico_enable_stdio_uart(general 0)
pico_add_extra_outputs(general)
