namespace YtDlpGui.Core;

public enum SiteKind
{
    Other,
    YouTube,
    Bilibili,
}

public enum MediaKind
{
    Video,
    Audio,
    Subtitle,
    Playlist,
}

public enum CookieSource
{
    None,
    ManualFile,
    Firefox,
    Edge,
    Chrome,
}

public enum TransferState
{
    Idle,
    Sniffing,
    ReadyToDownload,
    Downloading,
    Updating,
}

public sealed record MediaFormat(
    string Id,
    string Label,
    MediaKind Kind,
    bool HasAudio = false,
    string? PlaylistMode = null,
    string? PlaylistTitle = null,
    int? PlaylistCount = null,
    DirectMediaPayload? DirectPayload = null)
{
    public override string ToString() => Label;
}

public sealed record DirectMediaPayload(
    string Title,
    string Referer,
    string UserAgent,
    string? VideoUrl = null,
    string? AudioUrl = null);

public sealed record SniffRequest(
    string Url,
    string? ManualCookiePath = null,
    bool TryBrowserCookies = false);

public sealed record SniffResult(
    bool IsSuccess,
    string Message,
    IReadOnlyList<MediaFormat> Formats,
    CookieSource CookieSource = CookieSource.None,
    bool ShouldRequestManualCookies = false)
{
    public static SniffResult Failure(string message, bool shouldRequestManualCookies = false) =>
        new(false, message, [], CookieSource.None, shouldRequestManualCookies);
}

public sealed record DownloadRequest(
    string Url,
    MediaFormat Format,
    string OutputDirectory,
    CookieSource CookieSource,
    string? ManualCookiePath = null);

public sealed record DownloadResult(
    bool IsSuccess,
    bool IsCanceled,
    string Message,
    string? OutputPath = null);

public sealed record UpdateResult(bool IsSuccess, string Message, string? Version = null);

public sealed record ToolPaths(string YtDlpPath, string? FfmpegPath)
{
    public bool HasYtDlp => File.Exists(YtDlpPath);

    public bool HasFfmpeg => !string.IsNullOrWhiteSpace(FfmpegPath) && File.Exists(FfmpegPath);
}

public sealed record AppSettings(string OutputDirectory = "");
