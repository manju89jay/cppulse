// Test fixture: modernization rule violations.
// Expected findings: CPP-MOD-001 (c-style cast), CPP-MOD-002 (deprecated header),
//                    CPP-MOD-003 (missing override), CPP-MOD-008 (unscoped enum),
//                    CPP-MOD-009 (typedef)

#include <stdio.h>   // CPP-MOD-002: deprecated C header

// CPP-MOD-009: typedef instead of using
typedef int MyInt;
typedef unsigned long SizeType;

// CPP-MOD-008: unscoped enum
enum Color { Red, Green, Blue };

// CPP-MOD-001: C-style cast
void cast_example() {
    double val = 3.14;
    int truncated = (int)val;   // C-style cast
    (void)truncated;
}

// CPP-MOD-003: missing override
class Base {
public:
    virtual void process() {}
    virtual int compute(int x) { return x; }
    virtual ~Base() = default;
};

class Derived : public Base {
public:
    // Missing 'override' keyword
    virtual void process() {}   // CPP-MOD-003
    virtual int compute(int x) { return x * 2; }  // CPP-MOD-003
};
