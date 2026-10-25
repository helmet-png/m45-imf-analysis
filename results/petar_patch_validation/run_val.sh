# Same-IC runs with original / patch v1 / v2 / v2-instrumented PeTar, OMP_NUM_THREADS=1 (deterministic).
source ~/env.sh
N=$HOME/nbody
declare -A BIN=([orig]=$N/install/bin [v1]=$N/install_framefix/bin [v2]=$N/install_v2/bin [v2instr]=$N/install_v2instr/bin)
B=petar.omp.avx2.bse.galpy
for b in orig v1 v2 v2instr; do [ -x ${BIN[$b]}/$B ] || { echo "missing $b"; exit 1; }; done
start() {  # ic build extra-args tag
  ic=$1; b=$2; extra=$3; tag=$4
  src=~/m45_membership/runs_training/$ic
  nb=$(python3 -c "import json,re;c=json.load(open('$src/manifest.json'))['commands'][2];print(re.search(r' -b (\d+)',c).group(1))")
  d=~/runs_diag/patchval/$ic$tag/$b; rm -rf $d; mkdir -p $d; cp $src/input $d/
  (cd $d && OMP_NUM_THREADS=1 nohup ${BIN[$b]}/$B -u 1 -b $nb --bse-metallicity 0.02 --stellar-evolution 1 --detect-interrupt 1 --galpy-set MWPotential2014 -t 135.0 -o 5.0 $extra input > petar.log 2>&1 < /dev/null &)
  echo "started $ic$tag $b"
}
for ic in mb_train_0000_s40001 mb_train_0298_s40299; do
  for b in orig v1 v2 v2instr; do start $ic $b "" ""; done
done
# escaper-removal path (not used by the training grid): remove unbound stars beyond 20 pc
for b in orig v2instr; do start mb_train_0000_s40001 $b "--r-escape 20" "_esc20"; done
