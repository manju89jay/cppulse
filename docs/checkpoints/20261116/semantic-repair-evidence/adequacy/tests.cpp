#include <climits>
#include <cstring>
int clamp_value(int,int,int);
int main(int argc,char** argv) {
 if(argc!=2) return 2;
 const char* name=argv[1];
 if(std::strcmp(name,"lower")==0) return clamp_value(-3,0,10)==0?0:1;
 if(std::strcmp(name,"inside")==0) return clamp_value(5,0,10)==5?0:1;
 if(std::strcmp(name,"upper")==0) return clamp_value(14,0,10)==10?0:1;
 if(std::strcmp(name,"equal-bounds")==0) return clamp_value(INT_MIN,3,3)==3 && clamp_value(INT_MAX,3,3)==3?0:1;
 if(std::strcmp(name,"integer-extremes")==0) return clamp_value(INT_MIN,INT_MIN,INT_MAX)==INT_MIN && clamp_value(INT_MAX,INT_MIN,INT_MAX)==INT_MAX && clamp_value(INT_MAX,-1,1)==1?0:1;
 for(int lower=-5;lower<=5;++lower) for(int upper=lower;upper<=5;++upper) {
  int previous=lower;
  for(int value=-8;value<=8;++value) {
   int observed=clamp_value(value,lower,upper);
   if(std::strcmp(name,"range-and-identity")==0) {
    if(observed<lower || observed>upper || (value>=lower && value<=upper && observed!=value)) return 1;
   } else if(std::strcmp(name,"idempotence")==0) {
    if(clamp_value(observed,lower,upper)!=observed) return 1;
   } else if(std::strcmp(name,"monotonicity")==0) {
    if(observed<previous) return 1;
    previous=observed;
   } else return 2;
  }
 }
 return 0;
}
