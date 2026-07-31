using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using YtDlpGui.Core;

namespace YtDlpGui.App;

public partial class MainWindow : Window
{
    private const int WmSettingChange = 0x001A;
    private const int WmThemeChanged = 0x031A;

    private readonly MainViewModel _viewModel;
    private HwndSource? _windowSource;
    private bool _isInitialized;

    public MainWindow()
    {
        _viewModel = new();
        InitializeComponent();
        DataContext = _viewModel;
        Loaded += OnLoaded;
        SourceInitialized += OnSourceInitialized;
        Closing += OnClosing;
        _viewModel.NotificationRequested += ShowNotification;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        await _viewModel.InitializeAsync();
        ThemeManager.Apply(_viewModel.Theme);
        _isInitialized = true;
        UrlTextBox.Focus();
    }

    private async void PrimaryAction_Click(object sender, RoutedEventArgs e) =>
        await _viewModel.RunPrimaryActionAsync();

    private void Cancel_Click(object sender, RoutedEventArgs e) => _viewModel.CancelCurrentOperation();

    private async void UpdateYtDlp_Click(object sender, RoutedEventArgs e) =>
        await _viewModel.UpdateYtDlpAsync();

    private async void SaveCookie_Click(object sender, RoutedEventArgs e) =>
        await _viewModel.SaveManualCookieAsync();

    private async void ThemeComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_isInitialized || ThemeComboBox.SelectedValue is not AppTheme theme)
        {
            return;
        }

        ThemeManager.Apply(theme);
        await _viewModel.SetThemeAsync(theme);
    }

    private async void ChooseOutputDirectory_Click(object sender, RoutedEventArgs e)
    {
        var initialDirectory = Directory.Exists(_viewModel.OutputDirectory)
            ? _viewModel.OutputDirectory
            : Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var dialog = new ThemedFolderDialog(initialDirectory)
        {
            Owner = this,
        };

        if (dialog.ShowDialog() == true && dialog.SelectedDirectory is not null)
        {
            await _viewModel.SetOutputDirectoryAsync(dialog.SelectedDirectory);
        }
    }

    private void OpenOutputDirectory_Click(object sender, RoutedEventArgs e)
    {
        if (!Directory.Exists(_viewModel.OutputDirectory))
        {
            ShowNotification(new("错误", "输出目录不存在，请重新选择。", false));
            return;
        }

        var startInfo = new ProcessStartInfo("explorer.exe") { UseShellExecute = true };
        startInfo.ArgumentList.Add(_viewModel.OutputDirectory);
        Process.Start(startInfo);
    }

    private void ShowNotification(NotificationRequest notification)
    {
        ThemedMessageDialog.Show(
            this,
            notification.Title,
            notification.Message,
            notification.IsSuccess);
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        ThemeManager.ApplyWindowChrome(this);
        _windowSource = PresentationSource.FromVisual(this) as HwndSource;
        _windowSource?.AddHook(WindowMessageHook);
    }

    private void OnClosing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        _windowSource?.RemoveHook(WindowMessageHook);
        _viewModel.NotificationRequested -= ShowNotification;
        _viewModel.Dispose();
    }

    private IntPtr WindowMessageHook(
        IntPtr windowHandle,
        int message,
        IntPtr wordParameter,
        IntPtr longParameter,
        ref bool handled)
    {
        if (message is WmSettingChange or WmThemeChanged)
        {
            Dispatcher.BeginInvoke(ThemeManager.RefreshSystemTheme);
        }

        return IntPtr.Zero;
    }
}
