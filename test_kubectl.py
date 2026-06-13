import subprocess
print(subprocess.run(['bash', '-c', 'kubectl() { kubectl.exe "$@" < /dev/null; }; kubectl get pods -n gatekeeper-system -l control-plane=controller-manager | grep Running; echo Exit: $?'], capture_output=True, text=True).stdout)
