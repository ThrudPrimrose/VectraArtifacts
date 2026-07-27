cat > ~/env_setup.sh << 'EOF'
uenv start prgenv-gnu/26.3:v1 --view=default
export PATH="$SCRATCH/llvm-env/view/bin:$PATH"
export LD_LIBRARY_PATH="/capstor/scratch/cscs/abonsall/spack/opt/spack/linux-neoverse_v2/llvm-22.1.0-7cbo7abdfx4n4dj3db5xaokoj6wixbfc/lib/aarch64-unknown-linux-gnu:$LD_LIBRARY_PATH"
source ~/VectraArtifacts/daint_venv/bin/activate
which clang
clang --version
which python3
python3 -c "import dace; print(dace.__version__)"
EOF


cat > ~/env_setup.sh << 'EOF'
uenv start prgenv-gnu/26.3:v1 --view=default
export PATH="/capstor/scratch/cscs/abonsall/spack/opt/spack/linux-zen2/llvm-22.1.0-qzhmunohiks533awpifcf66rfhteykpb/bin:$PATH"
export LD_LIBRARY_PATH="/capstor/scratch/cscs/abonsall/spack/opt/spack/linux-zen2/llvm-22.1.0-qzhmunohiks533awpifcf66rfhteykpb/lib/x86_64-unknown-linux-gnu:$LD_LIBRARY_PATH"
source ~/VectraArtifacts/eiger_venv/bin/activate
which clang
clang --version
which python3
python3 -c "import dace; print(dace.__version__)"
EOF