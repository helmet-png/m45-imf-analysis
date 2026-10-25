set -e
source ~/env.sh
G=/home/albertren888_gmail_com/nbody/venv_galpy/lib/python3.12/site-packages/galpy
for v in v2 v2instr; do
  d=~/nbody/PeTar_$v; rm -rf $d; git clone -q ~/nbody/PeTar $d; cd $d; git checkout -q 84b81a8
  git apply ~/patches/patch_v2.patch
  [ $v = v2instr ] && python3 ~/patches/instrument.py $d
  ./configure --prefix=$HOME/nbody/install_$v --with-mpi=no --with-interrupt=bse --with-external=galpy --with-galpy-prefix=$G > configure.log 2>&1
  make -j3 > make.log 2>&1 && make install > install.log 2>&1
  ls $HOME/nbody/install_$v/bin/petar.omp.avx2.bse.galpy && echo "$v built"
done
