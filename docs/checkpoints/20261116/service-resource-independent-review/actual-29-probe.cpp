#include <cstdio>
#include "expected.h"
extern "C" int value();
extern "C" int preserved();
extern "C" int dependency();
int main(int argc, char** argv) {
 if(argc!=2) return 2;
 const bool behavior = value()==EXPECTED;
 const bool object = preserved()==7;
 const bool dep = dependency()==3;
 std::printf("{\"namespace\":\"%s\",\"cases\":{\"behavior\":%s,\"object\":%s,\"dependency\":%s},\"observations\":{}}\n",argv[1],behavior?"true":"false",object?"true":"false",dep?"true":"false");
 return behavior&&object&&dep?0:1;
}
