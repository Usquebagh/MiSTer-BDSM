#include "Vvector_line.h"
#include "common.hpp"
int main(int argc,char** argv){setup(argc,argv);try{
    Bench<Vvector_line> t(argc,argv);t.rtl.reset=1;t.rtl.line_valid=0;t.rtl.pixel_ready=0;t.tick();
    t.rtl.reset=0;t.rtl.x0=4;t.rtl.y0=6;t.rtl.x1=12;t.rtl.y1=6;t.rtl.intensity=128;
    t.rtl.line_valid=1;t.tick();t.rtl.line_valid=0;
    for(unsigned n=0;n<4;++n){t.check(t.rtl.pixel_valid&&t.rtl.pixel_x==2&&t.rtl.pixel_y==3,"stall_stability",2,t.rtl.pixel_x);t.tick();}
    t.rtl.pixel_ready=1;unsigned count=0;
    while(t.rtl.busy&&count<16){t.check(t.rtl.pixel_valid,"visible_pixel",1,t.rtl.pixel_valid);
        t.check(t.rtl.pixel_x==2+count,"pixel_x",2+count,t.rtl.pixel_x);
        t.check(t.rtl.pixel_y==3,"pixel_y",3,t.rtl.pixel_y);
        t.check(t.rtl.pixel_intensity==128,"pixel_intensity",128,t.rtl.pixel_intensity);++count;t.tick();}
    t.check(count==5,"pixel_count",5,count);t.check(t.rtl.done,"inclusive_completion",1,t.rtl.done);t.pass();return 0;
}catch(const Failure&){return 1;}}
