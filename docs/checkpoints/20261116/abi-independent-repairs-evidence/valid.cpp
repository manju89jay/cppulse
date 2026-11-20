struct S { int x; }; extern "C" int read(S* s) {return s->x;}
