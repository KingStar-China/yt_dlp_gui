using System.Windows;

namespace YtDlpGui.App;

public partial class ThemedMessageDialog : Window
{
    private ThemedMessageDialog(string title, string message, bool isSuccess)
    {
        InitializeComponent();
        Title = title;
        DialogTitleText.Text = title;
        DialogMessageText.Text = message;

        if (isSuccess)
        {
            IconText.Text = "✓";
            IconSurface.SetResourceReference(BackgroundProperty, "SuccessSurfaceBrush");
            IconText.SetResourceReference(ForegroundProperty, "AccentBrush");
        }

        SourceInitialized += (_, _) => ThemeManager.ApplyWindowChrome(this);
        ContentRendered += (_, _) => OkButton.Focus();
    }

    public static void Show(Window? owner, string title, string message, bool isSuccess)
    {
        var dialog = new ThemedMessageDialog(title, message, isSuccess);
        if (owner is { IsVisible: true })
        {
            dialog.Owner = owner;
        }
        else
        {
            dialog.WindowStartupLocation = WindowStartupLocation.CenterScreen;
        }

        _ = dialog.ShowDialog();
    }

    private void OkButton_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = true;
    }
}
