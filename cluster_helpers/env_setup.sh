cat > ~/env_setup.sh << 'EOF'
uenv start prgenv-gnu/26.3:v1 --view=default
export PATH="$SCRATCH/llvm-env/view/bin:$PATH"
source ~/VectraArtifacts/venv/bin/activate
which clang
clang --version
which python3
python3 -c "import dace; print(dace.__version__)"
EOF