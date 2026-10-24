//go:build windows

package main

import (
	"context"
	"os/exec"
	"strconv"
	"syscall"
	"time"

	"golang.org/x/sys/windows"
)

var (
	kernel32                     = syscall.NewLazyDLL("kernel32.dll")
	user32                       = syscall.NewLazyDLL("user32.dll")
	procGetConsoleWindow         = kernel32.NewProc("GetConsoleWindow")
	procAllocConsole             = kernel32.NewProc("AllocConsole")
	procShowWindow               = user32.NewProc("ShowWindow")
	procGenerateConsoleCtrlEvent = kernel32.NewProc("GenerateConsoleCtrlEvent")
)

// init allocates a console if missing (required for GenerateConsoleCtrlEvent)
// and immediately hides the console window to keep the GUI clean.
func init() {
	if hwnd, _, _ := procGetConsoleWindow.Call(); hwnd == 0 {
		procAllocConsole.Call()
		if h, _, _ := procGetConsoleWindow.Call(); h != 0 {
			procShowWindow.Call(h, uintptr(windows.SW_HIDE))
		}
	}
}

// createCommand creates a new command with the specified binary path and arguments,
// configured to run in a new process group without a visible window.
func createCommand(binPath string, args ...string) *exec.Cmd {
	cmd := exec.Command(binPath, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: windows.CREATE_NEW_PROCESS_GROUP | windows.CREATE_NO_WINDOW,
	}
	return cmd
}

// stopProcess sends a CTRL_C_EVENT to the process and waits for it to exit,
// forcibly killing the process tree if it doesn't exit within the timeout.
func stopProcess(cmd *exec.Cmd) error {
	if cmd == nil || cmd.Process == nil {
		return nil
	}

	r1, _, _ := procGenerateConsoleCtrlEvent.Call(syscall.CTRL_C_EVENT, uintptr(cmd.Process.Pid))
	if r1 != 0 {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()

		waitDone := make(chan error, 1)
		go func() {
			waitDone <- cmd.Wait()
		}()

		select {
		case err := <-waitDone:
			return err
		case <-ctx.Done():
		}
	}

	// Force kill process tree if still running
	killCmd := exec.Command("taskkill", "/F", "/T", "/PID", strconv.Itoa(cmd.Process.Pid))
	killCmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: windows.CREATE_NO_WINDOW,
	}
	return killCmd.Run()
}
