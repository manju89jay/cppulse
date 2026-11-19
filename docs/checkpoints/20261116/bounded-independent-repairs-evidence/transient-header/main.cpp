#include "a.hpp"
int value(int x) {
#if BRANCH
 if(x) return 1;
#endif
 return 0;
}
