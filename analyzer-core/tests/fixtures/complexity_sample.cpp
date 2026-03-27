// Test fixture: complexity rule violations.
// Expected findings: CPP-CX-002 (long function), CPP-CX-003 (too many params)

#include <cstddef>

// CPP-CX-003: too many parameters (>5 = warning, >8 = error)
int too_many_params(int a, int b, int c, int d, int e, int f, int g) {
    return a + b + c + d + e + f + g;
}

int way_too_many_params(int a, int b, int c, int d, int e, int f, int g, int h, int i) {
    return a + b + c + d + e + f + g + h + i;
}

// CPP-CX-002: function that is >80 lines long
// (padded with statements to exceed the threshold)
int long_function(int input) {
    int result = 0;
    result += input;
    result += 1;
    result += 2;
    result += 3;
    result += 4;
    result += 5;
    result += 6;
    result += 7;
    result += 8;
    result += 9;
    result += 10;
    result += 11;
    result += 12;
    result += 13;
    result += 14;
    result += 15;
    result += 16;
    result += 17;
    result += 18;
    result += 19;
    result += 20;
    result += 21;
    result += 22;
    result += 23;
    result += 24;
    result += 25;
    result += 26;
    result += 27;
    result += 28;
    result += 29;
    result += 30;
    result += 31;
    result += 32;
    result += 33;
    result += 34;
    result += 35;
    result += 36;
    result += 37;
    result += 38;
    result += 39;
    result += 40;
    result += 41;
    result += 42;
    result += 43;
    result += 44;
    result += 45;
    result += 46;
    result += 47;
    result += 48;
    result += 49;
    result += 50;
    result += 51;
    result += 52;
    result += 53;
    result += 54;
    result += 55;
    result += 56;
    result += 57;
    result += 58;
    result += 59;
    result += 60;
    result += 61;
    result += 62;
    result += 63;
    result += 64;
    result += 65;
    result += 66;
    result += 67;
    result += 68;
    result += 69;
    result += 70;
    result += 71;
    result += 72;
    result += 73;
    result += 74;
    result += 75;
    result += 76;
    result += 77;
    result += 78;
    result += 79;
    result += 80;
    return result;
}
