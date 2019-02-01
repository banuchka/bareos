#   BAREOS® - Backup Archiving REcovery Open Sourced
#
#   Copyright (C) 2017-2019 Bareos GmbH & Co. KG
#
#   This program is Free Software; you can redistribute it and/or
#   modify it under the terms of version three of the GNU Affero General Public
#   License as published by the Free Software Foundation and included
#   in the file LICENSE.
#
#   This program is distributed in the hope that it will be useful, but
#   WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#   02110-1301, USA.

IF(HAVE_WIN32)
   link_libraries(kernel32
      user32 gdi32 winspool shell32 ole32 oleaut32 uuid comdlg32 advapi32)
ENDIF()

IF(HAVE_OPENSSL)
  set(SSL_UNIT_TEST_FILES init_openssl.cc)
ENDIF()

set(LINK_LIBRARIES
   stored_objects
   dird_objects
   console_objects
   bareossd
   bareos
   bareoscats
   bareossql
   bareosfind
   ${LMDB_LIBS}
   ${NDMP_LIBS}
   ${JANSSON_LIBRARIES}
   ${GTEST_LIBRARIES}
   ${GTEST_MAIN_LIBRARIES})

IF(HAVE_PAM)
  LIST(APPEND LINK_LIBRARIES ${PAM_LIBRARIES})
ENDIF()
add_definitions(-DTEST_SMALL_HTABLE)

# where to find the certificates
add_definitions(-DCERTDIR=\"${PROJECT_SOURCE_DIR}/../regress/configs/BASE/tls\")

# where to find the source dir
add_definitions(-DPROJECT_SOURCE_DIR=\"${PROJECT_SOURCE_DIR}\")

####### test_lib ###############################
add_executable(test_lib
    alist_test.cc
    bareos_test_sockets.cc
    dlist_test.cc
    htable_test.cc
    qualified_resource_name_type_converter_test.cc
    lib_tests.cc
    ${PROJECT_SOURCE_DIR}/src/filed/evaluate_job_command.cc
    )

target_link_libraries(test_lib
   stored_objects
   bareossd
   bareos
   ${JANSSON_LIBRARIES}
   ${GTEST_LIBRARIES}
   ${GTEST_MAIN_LIBRARIES}
   )

add_test(NAME test_lib
   COMMAND test_lib
   )

set_property(TEST test_lib
   PROPERTY ENVIRONMENT "LD_LIBRARY_PATH=${CMAKE_BINARY_DIR}/src/lib:${CMAKE_BINARY_DIR}/src/stored"
   PROPERTY ENVIRONMENT "GTEST_COLOR=yes"
   )

add_dependencies(check test_lib)

####### test_output_formatter ###############################
add_executable(test_output_formatter
    lib_tests_output_formatter.cc
    )
target_link_libraries(test_output_formatter
   bareos
   ${JANSSON_LIBRARIES}
   ${GTEST_LIBRARIES}
   ${GTEST_MAIN_LIBRARIES}
   )

add_test(NAME test_output_formatter
   COMMAND test_output_formatter
   )

set_property(TEST test_output_formatter
   PROPERTY ENVIRONMENT "LD_LIBRARY_PATH=${CMAKE_BINARY_DIR}/src/lib:${CMAKE_BINARY_DIR}/src/stored"
   PROPERTY ENVIRONMENT "GTEST_COLOR=yes"
   )

add_dependencies(check test_output_formatter)

####### test_bsock ###############################
add_executable(test_bsock
    bsock_test.cc
    bareos_test_sockets.cc
    bsock_constructor_test.cc
    bsock_cert_verify_common_names_test.cc
    create_resource.cc
    ${SSL_UNIT_TEST_FILES}
    )
target_link_libraries(test_bsock ${LINK_LIBRARIES})
add_test(NAME test_bsock COMMAND test_bsock)



set_property(TEST test_bsock
   PROPERTY ENVIRONMENT "LD_LIBRARY_PATH=${CMAKE_BINARY_DIR}/src/lib:${CMAKE_BINARY_DIR}/src/stored:${CMAKE_BINARY_DIR}/src/cats:${CMAKE_BINARY_DIR}/src/findlib:${CMAKE_BINARY_DIR}/src/lmdb:${CMAKE_BINARY_DIR}/src/ndmp"
   PROPERTY ENVIRONMENT "GTEST_COLOR=yes"
   )

add_dependencies(check test_bsock)

####### test_connection_setup ###############################
add_executable(test_connection_setup
    bsock_test_connection_setup.cc
    ${SSL_UNIT_TEST_FILES}
)

target_link_libraries(test_connection_setup ${LINK_LIBRARIES})

add_test(NAME test_connection_setup COMMAND test_connection_setup)

set_property(TEST test_connection_setup
   PROPERTY ENVIRONMENT "LD_LIBRARY_PATH=${CMAKE_BINARY_DIR}/src/lib:${CMAKE_BINARY_DIR}/src/stored:${CMAKE_BINARY_DIR}/src/cats:${CMAKE_BINARY_DIR}/src/findlib:${CMAKE_BINARY_DIR}/src/lmdb:${CMAKE_BINARY_DIR}/src/ndmp"
   PROPERTY ENVIRONMENT "GTEST_COLOR=yes"
   )

add_dependencies(check test_connection_setup)



####### test_ndmp_address_translate ###############################
add_executable(test_ndmp_address_translate
  ndmp_address_translate_test.cc
  ../dird/ndmp_slot2elemaddr.cc
)

target_link_libraries(test_ndmp_address_translate ${LINK_LIBRARIES})

add_test(NAME test_ndmp_address_translate COMMAND test_ndmp_address_translate)

set_property(TEST test_ndmp_address_translate
   PROPERTY ENVIRONMENT "LD_LIBRARY_PATH=${CMAKE_BINARY_DIR}/src/lib:${CMAKE_BINARY_DIR}/src/stored:${CMAKE_BINARY_DIR}/src/cats:${CMAKE_BINARY_DIR}/src/findlib:${CMAKE_BINARY_DIR}/src/lmdb:${CMAKE_BINARY_DIR}/src/ndmp"
   PROPERTY ENVIRONMENT "GTEST_COLOR=yes"
   )

add_dependencies(check test_ndmp_address_translate)



