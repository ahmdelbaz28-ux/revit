using System;
using System.Windows.Controls;
using Autodesk.Revit.UI;
using Microsoft.Web.WebView2.Core;

namespace BazSparkRevitBridge
{
    /// <summary>
    /// Interaction logic for WebPanelPage.xaml hosting the BAZspark WebView2 panel in Revit.
    /// Implements IDockablePaneProvider to register as a Revit Dockable Pane.
    /// </summary>
    public partial class WebPanelPage : Page, IDockablePaneProvider
    {
        public WebPanelPage()
        {
            InitializeComponent();
            try
            {
                webView.Source = new Uri(GetDashboardUrl());
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[BAZspark config] Invalid URI format: {ex.Message}");
                webView.Source = new Uri("http://localhost:5173");
            }
            InitializeAsync();
        }

        private string GetDashboardUrl()
        {
            const string defaultUrl = "http://localhost:5173";
            try
            {
                string dllPath = System.IO.Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location) ?? "";
                string configPath = System.IO.Path.Combine(dllPath, "bazspark_config.json");
                if (System.IO.File.Exists(configPath))
                {
                    string json = System.IO.File.ReadAllText(configPath);
                    var config = Newtonsoft.Json.JsonConvert.DeserializeObject<System.Collections.Generic.Dictionary<string, string>>(json);
                    if (config != null && config.TryGetValue("DashboardUrl", out string url))
                    {
                        return url;
                    }
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[BAZspark config] Error reading config file: {ex.Message}");
            }
            return defaultUrl;
        }

        private async void InitializeAsync()
        {
            if (!IsWebView2Available())
            {
                webView.Visibility = System.Windows.Visibility.Collapsed;
                fallbackGrid.Visibility = System.Windows.Visibility.Visible;
                return;
            }

            try
            {
                // Ensure CoreWebView2 is initialized
                await webView.EnsureCoreWebView2Async(null);

                // Configure settings to behave like a native integrated panel
                webView.CoreWebView2.Settings.IsZoomControlEnabled = false;
                webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
                webView.CoreWebView2.Settings.AreDevToolsEnabled = true; // Keep dev tools available for debugging
                webView.CoreWebView2.Settings.IsBuiltInErrorPageEnabled = true;

                RegisterNavigationCompleted();
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[BAZspark Revit WebView2] Init failed: {ex.Message}");
                webView.Visibility = System.Windows.Visibility.Collapsed;
                fallbackGrid.Visibility = System.Windows.Visibility.Visible;
            }
        }

        private void RegisterNavigationCompleted()
        {
            webView.NavigationCompleted += async (sender, args) =>
            {
                if (args.IsSuccess)
                {
                    try
                    {
                        var context = new
                        {
                            appName = "Revit",
                            appVersion = "2024",
                            activeDocName = "",
                            activeDocPath = ""
                        };
                        string json = Newtonsoft.Json.JsonConvert.SerializeObject(context);
                        await webView.CoreWebView2.ExecuteScriptAsync($"window.bazsparkContext = {json};");
                    }
                    catch (Exception ex)
                    {
                        System.Diagnostics.Debug.WriteLine($"[BAZspark WebView2] Context injection failed: {ex.Message}");
                    }
                }
            };
        }

        private bool IsWebView2Available()
        {
            try
            {
                string version = CoreWebView2Environment.GetAvailableBrowserVersionString();
                return !string.IsNullOrEmpty(version);
            }
            catch
            {
                return false;
            }
        }

        private void DownloadButton_Click(object sender, System.Windows.RoutedEventArgs e)
        {
            try
            {
                System.Diagnostics.Process.Start("https://developer.microsoft.com/en-us/microsoft-edge/webview2/");
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[BAZspark WebView2] Failed to open download link: {ex.Message}");
            }
        }

        /// <summary>
        /// Registers the page control as the framework element for Revit's Dockable Pane.
        /// Sets default position tabbed behind the Project Browser.
        /// </summary>
        public void SetupDockablePane(DockablePaneProviderData data)
        {
            data.FrameworkElement = this;
            data.InitialState = new DockablePaneState
            {
                DockPosition = DockPosition.Tabbed,
                TabBehind = DockablePanes.BuiltInDockablePanes.ProjectBrowser
            };
        }
    }
}
