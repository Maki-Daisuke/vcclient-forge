package main

import "testing"

func TestResolveBackendCommand(t *testing.T) {
	bin, args, dir, err := resolveBackendCommand()
	if err != nil {
		t.Fatalf("resolveBackendCommand failed: %v", err)
	}
	if bin == "" {
		t.Errorf("expected non-empty binary path")
	}
	if len(args) == 0 {
		t.Errorf("expected non-empty args")
	}
	if dir == "" {
		t.Errorf("expected non-empty directory")
	}
}
