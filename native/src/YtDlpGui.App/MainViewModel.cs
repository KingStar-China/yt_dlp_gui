using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Runtime.CompilerServices;
using YtDlpGui.Core;
using YtDlpGui.Infrastructure;

namespace YtDlpGui.App;

public sealed record NotificationRequest(string Title, string Message, bool IsSuccess);

public sealed record ThemeOption(AppTheme Value, string Label)
{
    public override string ToString() => Label;
}

public sealed class MainViewModel : INotifyPropertyChanged, IDisposable
{
    private readonly IYtDlpService _ytDlpService;
    private readonly ISettingsStore _settingsStore;
    private readonly SemaphoreSlim _settingsSaveLock = new(1, 1);
    private readonly TransferStateMachine _stateMachine = new();
    private CancellationTokenSource? _operationCancellation;
    private string _url = string.Empty;
    private string _outputDirectory = string.Empty;
    private string _cookieText = string.Empty;
    private string _statusText = "正在初始化...";
    private string _toolSummary = "正在检查 yt-dlp 与 FFmpeg...";
    private string? _manualCookiePath;
    private SiteKind _manualCookieSite = SiteKind.Other;
    private string? _manualCookieHost;
    private CookieSource _activeCookieSource = CookieSource.None;
    private MediaFormat? _selectedFormat;
    private bool _isCookiePanelExpanded;
    private bool _tryBrowserCookies;
    private AppTheme _theme = AppTheme.System;
    private bool _disposed;

    public MainViewModel(IYtDlpService? ytDlpService = null, ISettingsStore? settingsStore = null)
    {
        _ytDlpService = ytDlpService ?? new YtDlpService();
        _settingsStore = settingsStore ?? new JsonSettingsStore();
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public event Action<NotificationRequest>? NotificationRequested;

    public ObservableCollection<MediaFormat> Formats { get; } = [];

    public IReadOnlyList<ThemeOption> ThemeOptions { get; } =
    [
        new(AppTheme.Dark, "深色"),
        new(AppTheme.Light, "浅色"),
        new(AppTheme.System, "跟随系统"),
    ];

    public string Url
    {
        get => _url;
        set
        {
            if (!SetField(ref _url, value))
            {
                return;
            }

            if (!_stateMachine.IsBusy)
            {
                ClearFormats();
                _stateMachine.Reset();
                _activeCookieSource = CookieSource.None;
                StatusText = string.IsNullOrWhiteSpace(value) ? "准备就绪" : "链接已变更，请重新嗅探";
                RefreshStateBindings();
            }

            OnPropertyChanged(nameof(CanSaveCookie));
            OnPropertyChanged(nameof(CookieScopeLabel));
            OnPropertyChanged(nameof(CanRunPrimaryAction));
        }
    }

    public string OutputDirectory
    {
        get => _outputDirectory;
        private set => SetField(ref _outputDirectory, value);
    }

    public AppTheme Theme
    {
        get => _theme;
        private set => SetField(ref _theme, value);
    }

    public string CookieText
    {
        get => _cookieText;
        set
        {
            if (SetField(ref _cookieText, value))
            {
                OnPropertyChanged(nameof(CanSaveCookie));
            }
        }
    }

    public MediaFormat? SelectedFormat
    {
        get => _selectedFormat;
        set
        {
            if (SetField(ref _selectedFormat, value))
            {
                OnPropertyChanged(nameof(CanRunPrimaryAction));
            }
        }
    }

    public bool IsCookiePanelExpanded
    {
        get => _isCookiePanelExpanded;
        set => SetField(ref _isCookiePanelExpanded, value);
    }

    public bool TryBrowserCookies
    {
        get => _tryBrowserCookies;
        set => SetField(ref _tryBrowserCookies, value);
    }

    public string StatusText
    {
        get => _statusText;
        private set => SetField(ref _statusText, value);
    }

    public string ToolSummary
    {
        get => _toolSummary;
        private set => SetField(ref _toolSummary, value);
    }

    public bool IsBusy => _stateMachine.IsBusy;

    public bool IsNotBusy => !IsBusy;

    public bool CanCancel => _stateMachine.CanCancel;

    public bool HasFormats => Formats.Count > 0;

    public bool CanRunPrimaryAction => !IsBusy
        && !string.IsNullOrWhiteSpace(Url)
        && (!HasFormats || SelectedFormat is not null);

    public bool CanSaveCookie => !IsBusy
        && !string.IsNullOrWhiteSpace(CookieText)
        && UrlInspector.TryCreateHttpUri(Url, out _);

    public string PrimaryButtonText => _stateMachine.PrimaryButtonText;

    public string StateLabel => _stateMachine.State switch
    {
        TransferState.Sniffing => "正在嗅探",
        TransferState.ReadyToDownload => "等待下载",
        TransferState.Downloading => "正在下载",
        TransferState.Updating => "正在更新",
        _ => "准备就绪",
    };

    public string CookieScopeLabel
    {
        get
        {
            if (string.IsNullOrWhiteSpace(_manualCookiePath) || !File.Exists(_manualCookiePath))
            {
                return "未设置";
            }

            return IsManualCookieValidForCurrentUrl()
                ? $"已临时保存 · {_manualCookieHost}"
                : $"已保存，但仅限 {_manualCookieHost}";
        }
    }

    public async Task InitializeAsync()
    {
        var settings = await _settingsStore.LoadAsync();
        OutputDirectory = settings.OutputDirectory;
        Theme = settings.Theme;
        var version = await _ytDlpService.GetYtDlpVersionAsync();
        UpdateToolSummary(version);
        StatusText = version is null
            ? "未找到 yt-dlp，请先点击“更新 yt-dlp”"
            : "准备就绪：粘贴链接后点击“开始嗅探”";
        RefreshStateBindings();
    }

    public async Task RunPrimaryActionAsync()
    {
        if (IsBusy)
        {
            return;
        }

        if (Formats.Count == 0)
        {
            await SniffAsync();
        }
        else
        {
            await DownloadAsync();
        }
    }

    public async Task UpdateYtDlpAsync()
    {
        if (IsBusy)
        {
            return;
        }

        _stateMachine.BeginUpdate();
        BeginOperation();
        StatusText = "正在更新 yt-dlp...";
        RefreshStateBindings();

        try
        {
            var result = await _ytDlpService.UpdateYtDlpAsync(
                new Progress<string>(message => StatusText = message),
                _operationCancellation!.Token);
            StatusText = result.Message;
            UpdateToolSummary(result.Version ?? await _ytDlpService.GetYtDlpVersionAsync());
            NotificationRequested?.Invoke(new(result.IsSuccess ? "更新完成" : "更新失败", result.Message, result.IsSuccess));
        }
        catch (OperationCanceledException)
        {
            StatusText = "yt-dlp 更新已取消";
        }
        catch (Exception exception)
        {
            StatusText = $"yt-dlp 更新失败：{exception.Message}";
            NotificationRequested?.Invoke(new("更新失败", StatusText, false));
        }
        finally
        {
            _stateMachine.CompleteUpdate(HasFormats);
            EndOperation();
            RefreshStateBindings();
        }
    }

    public void CancelCurrentOperation()
    {
        if (!CanCancel)
        {
            return;
        }

        StatusText = "正在取消当前任务...";
        _operationCancellation?.Cancel();
    }

    public async Task SetOutputDirectoryAsync(string outputDirectory)
    {
        if (!Directory.Exists(outputDirectory))
        {
            NotificationRequested?.Invoke(new("错误", "选择的输出目录不存在。", false));
            return;
        }

        OutputDirectory = outputDirectory;
        try
        {
            await SaveSettingsAsync();
            StatusText = $"输出目录已更新：{outputDirectory}";
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            StatusText = $"输出目录已选择，但保存设置失败：{exception.Message}";
            NotificationRequested?.Invoke(new("设置保存失败", StatusText, false));
        }
    }

    public async Task SetThemeAsync(AppTheme theme)
    {
        if (!Enum.IsDefined(theme) || Theme == theme)
        {
            return;
        }

        Theme = theme;
        try
        {
            await SaveSettingsAsync();
            StatusText = $"界面主题已切换为：{ThemeOptions.First(option => option.Value == theme).Label}";
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            StatusText = $"主题已切换，但保存设置失败：{exception.Message}";
            NotificationRequested?.Invoke(new("设置保存失败", StatusText, false));
        }
    }

    public async Task SaveManualCookieAsync()
    {
        if (!CanSaveCookie || !UrlInspector.TryCreateHttpUri(Url, out var uri) || uri is null)
        {
            NotificationRequested?.Invoke(new("Cookie 未保存", "请先输入有效视频 URL 和 Netscape 格式 Cookie。", false));
            return;
        }

        DeleteManualCookieFile();
        _manualCookiePath = Path.Combine(Path.GetTempPath(), $"yt_dlp_gui_native_cookie_{Guid.NewGuid():N}.txt");
        var content = CookieText.Trim();
        if (!content.StartsWith("# Netscape HTTP Cookie File", StringComparison.OrdinalIgnoreCase))
        {
            content = $"# Netscape HTTP Cookie File{Environment.NewLine}{content}";
        }

        try
        {
            await File.WriteAllTextAsync(_manualCookiePath, content);
            _manualCookieSite = UrlInspector.DetectSite(Url);
            _manualCookieHost = uri.Host;
            CookieText = string.Empty;
            IsCookiePanelExpanded = false;
            ClearFormats();
            _stateMachine.Reset();
            StatusText = $"Cookie 已临时保存，仅用于 {_manualCookieHost}";
            OnPropertyChanged(nameof(CookieScopeLabel));
            RefreshStateBindings();
            NotificationRequested?.Invoke(new("Cookie 已保存", "请重新点击“开始嗅探”。关闭程序后临时 Cookie 会自动删除。", true));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            DeleteManualCookieFile();
            StatusText = $"Cookie 保存失败：{exception.Message}";
            NotificationRequested?.Invoke(new("Cookie 保存失败", StatusText, false));
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _operationCancellation?.Cancel();
        _operationCancellation?.Dispose();
        DeleteManualCookieFile();
        if (_ytDlpService is IDisposable disposable)
        {
            disposable.Dispose();
        }
    }

    private async Task SniffAsync()
    {
        if (!UrlInspector.TryCreateHttpUri(Url, out _))
        {
            NotificationRequested?.Invoke(new("链接无效", "请输入有效的视频 URL（需包含 http:// 或 https://）。", false));
            return;
        }

        var knownPageMessage = UrlInspector.GetKnownNonVideoMessage(Url);
        if (knownPageMessage is not null)
        {
            NotificationRequested?.Invoke(new("链接不可下载", knownPageMessage, false));
            return;
        }

        _stateMachine.BeginSniff();
        BeginOperation();
        StatusText = "正在嗅探可下载的视频、音频和字幕...";
        RefreshStateBindings();

        try
        {
            var manualCookiePath = IsManualCookieValidForCurrentUrl() ? _manualCookiePath : null;
            var result = await _ytDlpService.SniffAsync(
                new(Url.Trim(), manualCookiePath, TryBrowserCookies),
                new Progress<string>(message => StatusText = message),
                _operationCancellation!.Token);

            if (result.IsSuccess)
            {
                foreach (var format in result.Formats)
                {
                    Formats.Add(format);
                }

                SelectedFormat = Formats.FirstOrDefault();
                _activeCookieSource = result.CookieSource;
                StatusText = $"嗅探完成，共找到 {Formats.Count} 个可下载选项";
                _stateMachine.CompleteSniff(hasFormats: true);
            }
            else
            {
                StatusText = result.Message;
                IsCookiePanelExpanded = result.ShouldRequestManualCookies;
                _stateMachine.CompleteSniff(hasFormats: false);
                NotificationRequested?.Invoke(new("嗅探失败", result.Message, false));
            }
        }
        catch (OperationCanceledException)
        {
            StatusText = "嗅探已取消";
            if (_stateMachine.State == TransferState.Sniffing)
            {
                _stateMachine.CompleteSniff(hasFormats: false);
            }
        }
        catch (Exception exception)
        {
            StatusText = $"嗅探失败：{exception.Message}";
            if (_stateMachine.State == TransferState.Sniffing)
            {
                _stateMachine.CompleteSniff(hasFormats: false);
            }
            NotificationRequested?.Invoke(new("嗅探失败", StatusText, false));
        }
        finally
        {
            EndOperation();
            RefreshStateBindings();
        }
    }

    private async Task DownloadAsync()
    {
        if (SelectedFormat is null)
        {
            NotificationRequested?.Invoke(new("未选择格式", "请选择需要下载的格式。", false));
            return;
        }

        if (!Directory.Exists(OutputDirectory))
        {
            NotificationRequested?.Invoke(new("输出目录无效", "请重新选择输出目录。", false));
            return;
        }

        _stateMachine.BeginDownload();
        BeginOperation();
        StatusText = "正在启动下载...";
        RefreshStateBindings();

        try
        {
            var manualCookiePath = _activeCookieSource == CookieSource.ManualFile && IsManualCookieValidForCurrentUrl()
                ? _manualCookiePath
                : null;
            var result = await _ytDlpService.DownloadAsync(
                new(Url.Trim(), SelectedFormat, OutputDirectory, _activeCookieSource, manualCookiePath),
                new Progress<string>(message => StatusText = message),
                _operationCancellation!.Token);
            StatusText = result.Message;
            if (!result.IsCanceled)
            {
                NotificationRequested?.Invoke(new(result.IsSuccess ? "下载完成" : "下载失败", result.Message, result.IsSuccess));
            }
        }
        catch (OperationCanceledException)
        {
            StatusText = "下载已取消";
        }
        catch (Exception exception)
        {
            StatusText = $"下载失败：{exception.Message}";
            NotificationRequested?.Invoke(new("下载失败", StatusText, false));
        }
        finally
        {
            _stateMachine.CompleteDownload();
            EndOperation();
            RefreshStateBindings();
        }
    }

    private bool IsManualCookieValidForCurrentUrl()
    {
        if (string.IsNullOrWhiteSpace(_manualCookiePath)
            || !File.Exists(_manualCookiePath)
            || !UrlInspector.TryCreateHttpUri(Url, out var uri)
            || uri is null)
        {
            return false;
        }

        var currentSite = UrlInspector.DetectSite(Url);
        return _manualCookieSite != SiteKind.Other
            ? currentSite == _manualCookieSite
            : string.Equals(uri.Host, _manualCookieHost, StringComparison.OrdinalIgnoreCase);
    }

    private void ClearFormats()
    {
        Formats.Clear();
        SelectedFormat = null;
        OnPropertyChanged(nameof(HasFormats));
    }

    private void BeginOperation()
    {
        _operationCancellation?.Dispose();
        _operationCancellation = new();
    }

    private void EndOperation()
    {
        _operationCancellation?.Dispose();
        _operationCancellation = null;
    }

    private void UpdateToolSummary(string? version)
    {
        var ytDlp = version is null ? "未找到" : version;
        var ffmpeg = _ytDlpService.Tools.HasFfmpeg ? "已找到" : "未找到";
        ToolSummary = $"yt-dlp：{ytDlp}    FFmpeg：{ffmpeg}";
    }

    private async Task SaveSettingsAsync()
    {
        await _settingsSaveLock.WaitAsync();
        try
        {
            await _settingsStore.SaveAsync(new(OutputDirectory, Theme));
        }
        finally
        {
            _settingsSaveLock.Release();
        }
    }

    private void DeleteManualCookieFile()
    {
        if (string.IsNullOrWhiteSpace(_manualCookiePath))
        {
            return;
        }

        try
        {
            if (File.Exists(_manualCookiePath))
            {
                File.Delete(_manualCookiePath);
            }
        }
        catch (IOException)
        {
            // Best-effort cleanup; the temp directory remains user scoped.
        }

        _manualCookiePath = null;
        _manualCookieHost = null;
        _manualCookieSite = SiteKind.Other;
    }

    private void RefreshStateBindings()
    {
        OnPropertyChanged(nameof(IsBusy));
        OnPropertyChanged(nameof(IsNotBusy));
        OnPropertyChanged(nameof(CanCancel));
        OnPropertyChanged(nameof(HasFormats));
        OnPropertyChanged(nameof(CanRunPrimaryAction));
        OnPropertyChanged(nameof(CanSaveCookie));
        OnPropertyChanged(nameof(PrimaryButtonText));
        OnPropertyChanged(nameof(StateLabel));
    }

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return false;
        }

        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new(propertyName));
}
