
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <sys/resource.h>
#include <unistd.h>
static void soft(int) { _exit(78); }
int main(int argc,char** argv) {
 if(argc!=2) return 2;
 if(std::strcmp(argv[1],"memory")==0) {
  void* p=std::malloc(128UL*1024*1024);
  if(!p) return 42;
  static_cast<volatile char*>(p)[0]=1;
  std::free(p);return 0;
 }
 if(std::strcmp(argv[1],"soft")==0) std::signal(SIGXCPU,soft);
 else if(std::strcmp(argv[1],"hard")==0) std::signal(SIGXCPU,SIG_IGN);
 else return 2;
 for(;;) { asm volatile("" ::: "memory"); }
}
