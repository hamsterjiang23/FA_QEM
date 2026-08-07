#pragma once

#include <iostream>

using std::cerr;
using std::cin;
using std::cout;
using std::endl;
using std::istream;
using std::ostream;

// Pre-standard iostreams accepted string literals as input delimiters.
inline std::istream& operator>>(std::istream& stream, const char* delimiter) {
    for (const char* cursor = delimiter; *cursor != '\0' && stream; ++cursor) {
        char value = '\0';
        stream >> value;
        if (value != *cursor) stream.setstate(std::ios::failbit);
    }
    return stream;
}
