"""Add per-site audit counters to a PeTar tree that already has patch v2 applied.
Diagnostic build only. Sites: 1 SDAR group, 2 Hermite group, 3 hard single (hard.hpp);
4 escaper removal, 5 soft single (petar.hpp)."""
import sys, re
src = sys.argv[1] + "/src/"
open(src + "frame_audit.hpp", "w").write(r'''#pragma once
#include <iostream>
#include <iomanip>
//! diagnostic only: cumulative per-site record of moving-frame kinetic-energy corrections
struct FrameShiftAudit {
    enum { N = 5 };
    static double* cnt() { static double a[N] = {0}; return a; }
    static double* dm()  { static double a[N] = {0}; return a; }
    static double* de()  { static double a[N] = {0}; return a; }
    static double* hv()  { static double a[N] = {0}; return a; }
    static void add(int s, double dmass, double dE, double half_dm_v2) {
        double* c = cnt(); double* m = dm(); double* e = de(); double* h = hv();
#pragma omp atomic
        c[s] += 1.0;
#pragma omp atomic
        m[s] += dmass;
#pragma omp atomic
        e[s] += dE;
#pragma omp atomic
        h[s] += half_dm_v2;
    }
    template <class OS> static void print(OS& f) {
        std::streamsize p = f.precision(17);
        f << "FrameShiftAudit:";
        for (int s = 0; s < N; s++) f << " S" << s + 1 << " " << cnt()[s] << " " << dm()[s] << " " << de()[s] << " " << hv()[s];
        f << std::endl;
        f.precision(p);
    }
};
''')
s = open(src + "soft_ptcl.hpp").read()
anchor = "    return V*(_m1*_v1 - _m0*_v0) + 0.5*(_m1 - _m0)*(V*V);\n}\n"
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + r'''
inline PS::F64 calcDEKinFrameShiftAudit(const int _site, const PS::F64 _m1, const PS::F64vec& _v1,
                                        const PS::F64 _m0, const PS::F64vec& _v0) {
    const PS::F64 de = calcDEKinFrameShift(_m1, _v1, _m0, _v0);
    const PS::F64vec& V = FrameVelocity::vel();
    FrameShiftAudit::add(_site, _m1 - _m0, de, 0.5*(_m1 - _m0)*(V*V));
    return de;
}
''')
s = '#include "frame_audit.hpp"\n' + s
open(src + "soft_ptcl.hpp", "w").write(s)
for fn, sites in (("hard.hpp", [0, 1, 2]), ("petar.hpp", [3, 4])):
    t = open(src + fn).read()
    parts = t.split("calcDEKinFrameShift(")
    assert len(parts) == len(sites) + 1, (fn, len(parts) - 1)
    out = parts[0]
    for site, rest in zip(sites, parts[1:]):
        out += f"calcDEKinFrameShiftAudit({site}, " + rest
    open(src + fn, "w").write(out)
e = open(src + "energy.hpp").read()
anchor = '''             <<"  |L|: "<<Lt
             <<std::endl;
'''
assert e.count(anchor) == 1
e = e.replace(anchor, anchor + "        FrameShiftAudit::print(_fout);\n")
e = '#include "frame_audit.hpp"\n' + e
open(src + "energy.hpp", "w").write(e)
print("instrumented OK")
