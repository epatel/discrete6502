# Optional built-in test images. Included by any firmware that compiles
# functest.c -- see common/functest_images.h for the licensing reason this is a
# switch rather than the default.
#
# Default OFF. The configure-time message below is the "do you want this?"
# prompt: CMake is non-interactive by contract, so an actual prompt would break
# scripted builds and re-ask on every fresh build directory.

get_filename_component(D6502_COMMON_DIR ${CMAKE_CURRENT_LIST_DIR} ABSOLUTE)
get_filename_component(D6502_ROOT ${D6502_COMMON_DIR}/../.. ABSOLUTE)

option(EMBED_FUNCTEST
    "Compile Klaus Dormann's GPLv3 test images into the firmware (see gen/functest/README.md)"
    OFF)

function(discrete6502_add_functest_images target)
    if(EMBED_FUNCTEST)
        find_package(Python3 COMPONENTS Interpreter REQUIRED)
        set(gen ${D6502_COMMON_DIR}/functest_images.c)
        add_custom_command(
            OUTPUT ${gen}
            COMMAND ${Python3_EXECUTABLE}
                    ${D6502_ROOT}/tools/embed_functest.py --out ${gen}
            DEPENDS ${D6502_ROOT}/tools/embed_functest.py
                    ${D6502_ROOT}/tools/build_functest.py
                    ${D6502_ROOT}/gen/functest/6502_functional_test.hex
                    ${D6502_ROOT}/gen/functest/6502_functional_test_traps.csv
                    ${D6502_ROOT}/gen/functest/6502_decimal_test.hex
                    ${D6502_ROOT}/gen/functest/6502_decimal_test_traps.csv
            COMMENT "Generating functest_images.c (GPLv3 images -- gitignored)"
            VERBATIM)
        target_sources(${target} PRIVATE ${gen})
        message(STATUS "functest images: EMBEDDED")
        message(STATUS "  the resulting binary is a combined work with GPLv3 code")
        message(STATUS "  -- fine to build and use, do not redistribute it")
    else()
        target_sources(${target} PRIVATE ${D6502_COMMON_DIR}/functest_images_none.c)
        message(STATUS "functest images: not embedded (GPLv3 -- gen/functest/README.md)")
        message(STATUS "  to embed: cmake -DEMBED_FUNCTEST=ON ..")
    endif()
endfunction()
