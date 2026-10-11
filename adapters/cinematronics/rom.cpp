#include "Vcinemat_rom.h"
#include "common.hpp"
int main(int argc,char** argv){setup(argc,argv);try{
    Bench<Vcinemat_rom> t(argc,argv);t.rtl.rom_16k=0;t.rtl.cpu_addr=0;
    auto pattern=[](unsigned a){return (a^(a>>8)^(a>>12))&255;};
    t.rtl.load_write=1;for(unsigned a=0;a<16384;++a){t.rtl.load_addr=a;t.rtl.load_data=pattern(a);t.tick();}
    t.rtl.load_write=0;
    for(unsigned map=0;map<2;++map){t.rtl.rom_16k=map;
        for(unsigned a=0;a<65536;++a){t.rtl.cpu_addr=a;t.tick();
            // Logical banks 0/1 -> physical bank 0; 2/3 -> physical bank 1.
            unsigned physical=map?(a%16384):((a/8192)%2)*4096+(a%4096);
            t.check(t.rtl.cpu_data==pattern(physical),"rom_byte",pattern(physical),t.rtl.cpu_data);
        }
    }t.pass();return 0;
}catch(const Failure&){return 1;}}
