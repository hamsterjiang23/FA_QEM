#ifndef GFXTOOLS_BUFFER_INCLUDED
#define GFXTOOLS_BUFFER_INCLUDED

#include <gfx/tools/Array.h>

template<class T>
class buffer : public array<T> {
protected:
    int fill;
public:
    buffer() { init(8); }
    buffer(int length) { init(length); }

    inline void init(int length) { array<T>::init(length); fill = 0; }
    inline int add(const T& value);
    inline void reset() { fill = 0; }
    inline int find(const T& value);
    inline T remove(int index);
    inline int addAll(const buffer<T>& source);
    inline void removeDuplicates();
    inline int length() const { return fill; }
    inline int maxLength() const { return this->len; }
};

template<class T>
inline int buffer<T>::add(const T& value) {
    if (fill == this->len) this->resize(this->len * 2);
    this->data[fill] = value;
    return fill++;
}

template<class T>
inline int buffer<T>::find(const T& value) {
    for (int index = 0; index < fill; ++index) {
        if (this->data[index] == value) return index;
    }
    return -1;
}

template<class T>
inline T buffer<T>::remove(int index) {
    --fill;
    T value = this->data[index];
    this->data[index] = this->data[fill];
    return value;
}

template<class T>
inline int buffer<T>::addAll(const buffer<T>& source) {
    for (int index = 0; index < source.fill; ++index) add(source(index));
    return fill;
}

template<class T>
inline void buffer<T>::removeDuplicates() {
    for (int index = 0; index < fill; ++index) {
        for (int compare = index + 1; compare < fill;) {
            if (this->data[compare] == this->data[index]) remove(compare);
            else ++compare;
        }
    }
}

#endif

