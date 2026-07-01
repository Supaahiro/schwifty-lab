using ApiResilience.Contracts;
using ApiResilience.Logger;
using ApiResilience.Server;
using ApiResilience.Server.Components;
using Microsoft.AspNetCore.Http.Features;
using Scalar.AspNetCore;

var builder = WebApplication.CreateBuilder(args);

// Configure application configuration sources
builder.Configuration.AddJsonFile("appsettings.json", optional: false, reloadOnChange: true);
builder.Configuration.AddEnvironmentVariables();
builder.Configuration.AddCommandLine(args);
builder.Configuration.AddUserSecrets<Program>();

// Add logging
builder.Services.AddLogging(builder =>
{
    builder.ClearProviders();
    builder.AddColorConsoleLogger();
});

// Add services to the container.
// Learn more about configuring OpenAPI at https://aka.ms/aspnet/openapi
builder.Services.AddOpenApi();

// Add error handling middleware with custom problem details
builder.Services.AddProblemDetails(options =>
{
    options.CustomizeProblemDetails = context =>
    {
        // Sets the instance to the HTTP method and path of the request.
        context.ProblemDetails.Instance = $"{context.HttpContext.Request.Method} {context.HttpContext.Request.Path}";

        // Cache the extensions dictionary to avoid repeating the member-access chain.
        var extensions = context.ProblemDetails.Extensions;

        // Adds the request ID to the problem details extensions.
        extensions.TryAdd("messageId", context.HttpContext.TraceIdentifier);

        // Adds the trace ID from the activity feature to the problem details extensions.
        var activity = context.HttpContext.Features.Get<IHttpActivityFeature>()?.Activity;
        extensions.TryAdd("traceId", activity);
    };
});
builder.Services.AddExceptionHandler<GlobalExceptionHandler>();

// Configure and validate ServerSettings
builder.Services.AddOptions<ServerSettings>()
    .Bind(builder.Configuration.GetSection(ServerSettings.SectionName))
    .ValidateDataAnnotations()
    .ValidateOnStart();

// Register RuntimeServerSettingsService as singleton for runtime configuration
builder.Services.AddSingleton<ServerSettingsService>();

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

var app = builder.Build();

// Track application startup time and define warmup period
var appStartTime = DateTimeOffset.UtcNow;

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
    app.MapScalarApiReference();
}

app.UseMiddleware<RequestTimingMiddleware>();
app.UseExceptionHandler();
app.UseHttpsRedirection();
app.UseAntiforgery();
app.MapStaticAssets();
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

var summaries = new[] { "Freezing", "Bracing", "Chilly", "Cool", "Mild", "Warm", "Balmy", "Hot", "Sweltering", "Scorching" };

// Define the weather forecast endpoint
app.MapGet("/weatherforecast", async (ServerSettingsService settingsService) =>
{
    var serverSettings = settingsService.GetRuntimeSettings();

    // After the warmup period, introduce random delays and errors
    var elapsedSeconds = (DateTimeOffset.UtcNow - appStartTime).TotalSeconds;
    if (elapsedSeconds >= serverSettings.WarmupSeconds)
    {
        var chance = Random.Shared.NextDouble();
        if (chance < serverSettings.ErrorProbability)
            throw new ResponseInternalErrorException("Something went wrong while fetching the weather forecast."); 
        else if (chance < serverSettings.ErrorProbability + serverSettings.DelayProbability)
            await Task.Delay(serverSettings.DelayDurationMs);
    }

    // Happy path: return a 5-day weather forecast
    var forecast = Enumerable.Range(1, 5).Select(index =>
          new WeatherForecast
          (
              DateOnly.FromDateTime(DateTime.UtcNow.AddDays(index)),
              Random.Shared.Next(-20, 55),
              summaries[Random.Shared.Next(summaries.Length)]
          ))
          .ToArray();
    return forecast;
})
.WithName("GetWeatherForecast").AllowAnonymous();

app.Run();