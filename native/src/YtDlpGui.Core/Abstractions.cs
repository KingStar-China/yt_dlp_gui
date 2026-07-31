namespace YtDlpGui.Core;

public interface IYtDlpService
{
    ToolPaths Tools { get; }

    Task<SniffResult> SniffAsync(
        SniffRequest request,
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default);

    Task<DownloadResult> DownloadAsync(
        DownloadRequest request,
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default);

    Task<UpdateResult> UpdateYtDlpAsync(
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default);

    Task<string?> GetYtDlpVersionAsync(CancellationToken cancellationToken = default);
}

public interface ISettingsStore
{
    Task<AppSettings> LoadAsync(CancellationToken cancellationToken = default);

    Task SaveAsync(AppSettings settings, CancellationToken cancellationToken = default);
}
