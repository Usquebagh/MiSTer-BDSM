#include "Vstarcastle_sound.h"
#include "common.hpp"
int main(int argc,char** argv){setup(argc,argv);try{
    Bench<Vstarcastle_sound> t(argc,argv);t.rtl.reset=1;t.rtl.outputs=0x0e;t.tick();
    t.check(t.rtl.audio==0,"reset_silence",0,t.rtl.audio);t.rtl.reset=0;t.tick();
    // OUT7 data, rising OUT4 shifts, rising OUT0 commits. Non-symmetric pattern.
    unsigned old=t.rtl.sound_latch,value=0xa6;t.rtl.outputs&=~0x11;t.tick();
    for(int bit=7;bit>=0;--bit){t.rtl.outputs=(t.rtl.outputs&~0x90)|(((value>>bit)&1)<<7);t.tick();
        t.rtl.outputs|=0x10;t.tick();t.rtl.outputs&=~0x10;t.tick();
        t.check(t.rtl.sound_latch==old,"latch_isolation",old,t.rtl.sound_latch);}
    t.check(t.rtl.shift_register==value,"serial_order",value,t.rtl.shift_register);
    t.rtl.outputs|=1;t.tick();t.check(t.rtl.sound_latch==value,"latch_commit",value,t.rtl.sound_latch);
    t.rtl.reset=1;t.rtl.outputs=0x0e;t.tick();t.rtl.reset=0;
    unsigned count=0;uint64_t last=0;
    for(unsigned n=0;n<2500000;++n){t.rtl.clk=0;t.rtl.eval();bool ce=t.rtl.sample_ce;t.tick();
        if(ce){++count;if(last)t.check(t.cycle-last==520||t.cycle-last==521,"sample_interval",520,t.cycle-last);last=t.cycle;}}
    t.check(count==4800,"sample_count",4800,count);t.pass();return 0;
}catch(const Failure&){return 1;}}
