using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;

namespace YtDlpGui.Infrastructure;

internal sealed record ProcessResult(int ExitCode, string StandardOutput, string StandardError)
{
    public string CombinedOutput => string.Join(
        Environment.NewLine,
        new[] { StandardOutput, StandardError }.Where(value => !string.IsNullOrWhiteSpace(value)));
}

internal sealed class ProcessRunner
{
    public async Task<ProcessResult> RunCaptureAsync(
        string executable,
        IReadOnlyList<string> arguments,
        CancellationToken cancellationToken)
    {
        using var process = CreateProcess(executable, arguments);
        if (!process.Start())
        {
            throw new InvalidOperationException($"无法启动 {Path.GetFileName(executable)}。");
        }

        using var cancellationRegistration = cancellationToken.Register(() => TryKill(process));
        var standardOutput = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var standardError = process.StandardError.ReadToEndAsync(cancellationToken);

        try
        {
            await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
            return new(
                process.ExitCode,
                await standardOutput.ConfigureAwait(false),
                await standardError.ConfigureAwait(false));
        }
        catch (OperationCanceledException)
        {
            TryKill(process);
            await WaitForExitAfterCancellationAsync(process).ConfigureAwait(false);
            throw;
        }
    }

    public async Task<ProcessResult> RunStreamingAsync(
        string executable,
        IReadOnlyList<string> arguments,
        Action<string>? lineReceived,
        CancellationToken cancellationToken)
    {
        using var process = CreateProcess(executable, arguments);
        if (!process.Start())
        {
            throw new InvalidOperationException($"无法启动 {Path.GetFileName(executable)}。");
        }

        using var cancellationRegistration = cancellationToken.Register(() => TryKill(process));
        var outputLines = new ConcurrentQueue<string>();
        var errorLines = new ConcurrentQueue<string>();
        var outputTask = PumpLinesAsync(process.StandardOutput, outputLines, lineReceived, cancellationToken);
        var errorTask = PumpLinesAsync(process.StandardError, errorLines, lineReceived, cancellationToken);

        try
        {
            await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
            await Task.WhenAll(outputTask, errorTask).ConfigureAwait(false);
            return new(process.ExitCode, string.Join(Environment.NewLine, outputLines), string.Join(Environment.NewLine, errorLines));
        }
        catch (OperationCanceledException)
        {
            TryKill(process);
            await WaitForExitAfterCancellationAsync(process).ConfigureAwait(false);
            throw;
        }
    }

    private static Process CreateProcess(string executable, IReadOnlyList<string> arguments)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = executable,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        startInfo.Environment["PYTHONUTF8"] = "1";
        startInfo.Environment["NO_COLOR"] = "1";
        foreach (var argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        return new() { StartInfo = startInfo, EnableRaisingEvents = true };
    }

    private static async Task PumpLinesAsync(
        StreamReader reader,
        ConcurrentQueue<string> lines,
        Action<string>? lineReceived,
        CancellationToken cancellationToken)
    {
        while (true)
        {
            var line = await reader.ReadLineAsync(cancellationToken).ConfigureAwait(false);
            if (line is null)
            {
                return;
            }

            var trimmed = line.Trim();
            if (trimmed.Length == 0)
            {
                continue;
            }

            lines.Enqueue(trimmed);
            lineReceived?.Invoke(trimmed);
        }
    }

    private static void TryKill(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
        }
        catch (InvalidOperationException)
        {
            // Process has already exited.
        }
        catch (System.ComponentModel.Win32Exception)
        {
            // The process may have exited between HasExited and Kill.
        }
    }

    private static async Task WaitForExitAfterCancellationAsync(Process process)
    {
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            await process.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            TryKill(process);
        }
    }
}
