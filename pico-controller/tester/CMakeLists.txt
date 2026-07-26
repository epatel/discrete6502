cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2_w CACHE STRING "Board type")
include(${CMAKE_CURRENT_LIST_DIR}/../common/pico_sdk_import.cmake)
project(discrete6502_tester C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()
add_executable(tester main.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/bus6502.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/functest.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/ihex.c)
target_include_directories(tester PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../common)
target_link_libraries(tester pico_stdlib)
pico_enable_stdio_usb(tester 1)
pico_enable_stdio_uart(tester 0)
pico_add_extra_outputs(tester)
