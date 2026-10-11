#include "Vcinemat_machine.h"
#include "common.hpp"
#include <vector>
int main(int argc,char** argv){setup(argc,argv);try{
    Bench<Vcinemat_machine> t(argc,argv);t.rtl.reset=1;t.rtl.game_id=0;t.rtl.load_active=1;t.rtl.rom_loaded=0;t.rtl.load_write=0;
    t.rtl.start1=0;t.rtl.start2=0;t.rtl.left=0;t.rtl.right=0;t.rtl.thrust=0;t.rtl.fire=0;t.rtl.coin=0;t.rtl.service=0;
    t.rtl.left2=0;t.rtl.right2=0;t.rtl.thrust2=0;t.rtl.fire2=0;t.rtl.dips=63;t.rtl.scan_x=0;t.rtl.scan_y=0;t.tick();t.rtl.reset=0;
    // ROM-free subset of the existing pinned-MAME checked synthetic fixture.
    std::vector<unsigned> code={0x00,0x95,0x21,0x95,0x00,0x95,0x04,0x57,0x03,0xee,0xf0,
        0x02,0x57,0x02,0xe0,0x00,0xd0,0xf7,0xe5,0x40,0x00,0x58};
    t.rtl.load_write=1;
    for(unsigned n=0;n<8192;++n){t.rtl.load_addr=n;t.rtl.load_data=n<code.size()?code[n]:0x5f;t.tick();
        t.check(!t.rtl.retired,"loading_blocks_execution",0,t.rtl.retired);}
    t.rtl.load_write=0;t.rtl.load_active=0;t.rtl.rom_loaded=1;
    unsigned elapsed=0;while(!t.rtl.machine_ready&&elapsed<200000){t.tick();++elapsed;}
    t.check(t.rtl.machine_ready,"startup_deadline",1,t.rtl.machine_ready);
    unsigned retired=0,vectors=0;for(unsigned n=0;n<10000;++n){bool accepted=t.rtl.vector_valid&&t.rtl.vector_ready;t.tick();retired+=t.rtl.retired;vectors+=accepted;}
    t.check(retired>=10,"retirement_progress",10,retired);t.check(vectors>0,"vector_activity",1,vectors);
    t.rtl.load_active=1;t.rtl.rom_loaded=0;t.tick();t.check(!t.rtl.machine_ready,"reload_blocks_execution",0,t.rtl.machine_ready);
    t.pass();return 0;
}catch(const Failure&){return 1;}}
