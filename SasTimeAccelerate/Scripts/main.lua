-- SasTimeAccelerate: speed up the game's time while sailing.
--   Ctrl+Alt+Numpad +  next speed up  (1, 2, 4, 8)
--   Ctrl+Alt+Numpad -  next speed down
--   Ctrl+Alt+Numpad 0  back to normal speed at once
-- (Not PageUp/PageDown or Home: the game uses those for the engine, and ignores Ctrl and Alt.)
-- The speed is the game's global time dilation, so the world, the boat and the calendar all run faster
-- together (the calendar and the world clock follow it; measured at 4x). The game always starts at normal
-- speed, whatever it was left at, and goes back to normal when a save is loaded.
--
-- While the speed is above normal the log gets a line every few seconds: how fast the world clock really
-- runs against the wall clock, the nearest boat's speed, heel and trim, and the calendar, so that what a
-- speed does to a boat can be read afterwards.

-- Which copy of this script is running. The log says a release name and a checksum of the file itself, so
-- there is never a doubt whether the game loaded the version that was meant to be deployed.
SCRIPT_VERSION = "2026-10-17.2"
function ScriptChecksum()
    local file = io.open(debug.getinfo(1, "S").source:sub(2), "rb")
    if not file then return "unreadable", 0 end
    local text = file:read("*a")
    file:close()
    local hash = 2166136261  -- FNV-1a, 32 bits
    for i = 1, #text do hash = ((hash ~ text:byte(i)) * 16777619) & 0xFFFFFFFF end
    return string.format("%08X", hash), #text
end
do
    local checksum, bytes = ScriptChecksum()
    print("[SasTimeAccelerate] version " .. SCRIPT_VERSION .. ", file checksum " .. checksum .. " (" .. bytes .. " bytes)\n")
end

local SPEEDS = { 1, 2, 4, 8 }
local TELEMETRY_S = 5
local TOAST_CHANNEL = "Channel.Toast.Simple.Info"
local KNOTS_PER_CM_S = 1 / 51.4444

local Index = 1
local Wanted = nil        -- "up", "down" or "home", set by key presses, done on the game thread
local Started = false
local LastReal, LastWorld, LastReport = nil, nil, -math.huge

local function Log(text)
    print("[SasTimeAccelerate] " .. text .. "\n")
end

local function Controller()
    local controller = FindFirstOf("PlayerController")
    if controller and controller:IsValid() then return controller end
    return nil
end

local function Statics()
    return StaticFindObject("/Script/Engine.Default__GameplayStatics")
end

local function Toast(text)
    Log(text)
    pcall(function()
        local library = StaticFindObject("/Script/SasGameplayMessageSystem.Default__SasToastFunctionLibrary")
        local controller = Controller()
        library:SendSimpleToast(controller, { TagName = FName(TOAST_CHANNEL) }, FText(text), controller)
    end)
end

-- Sets the speed. False when the game is not ready (no player yet).
local function Apply(speed)
    local controller, statics = Controller(), Statics()
    if not controller or not statics then return false end
    statics:SetGlobalTimeDilation(controller, speed)
    LastReal, LastWorld = nil, nil
    return true
end

local function NearestBoat(here)
    local best, bestDist = nil, math.huge
    for _, boat in ipairs(FindAllOf("Boat") or {}) do
        pcall(function()
            if boat:GetFullName():find("Default__", 1, true) then return end
            local at = boat:K2_GetActorLocation()
            local d = (at.X - here.X) ^ 2 + (at.Y - here.Y) ^ 2
            if d < bestDist then best, bestDist = boat, d end
        end)
    end
    return best
end

local function Report()
    local controller, statics = Controller(), Statics()
    if not controller or not statics then return end
    local here = controller.Pawn:K2_GetActorLocation()
    local worldNow = statics:GetTimeSeconds(controller)
    local realNow = os.clock()
    local rate = "?"
    if LastReal and realNow > LastReal then rate = string.format("%.2f", (worldNow - LastWorld) / (realNow - LastReal)) end
    LastReal, LastWorld = realNow, worldNow
    local boatText = "no boat"
    local boat = NearestBoat(here)
    if boat then
        local velocity, rotation = boat:GetVelocity(), boat:K2_GetActorRotation()
        local knots = math.sqrt(velocity.X ^ 2 + velocity.Y ^ 2) * KNOTS_PER_CM_S
        boatText = string.format("%s %.1f kn, roll %.1f, pitch %.1f, heading %.0f, Z %.0f",
            boat:GetFullName():match("([%w_]+)$") or "?", knots, rotation.Roll, rotation.Pitch, rotation.Yaw,
            boat:K2_GetActorLocation().Z)
    end
    local calendar = "?"
    pcall(function()
        local sub = FindFirstOf("CalendarSubsystem")
        calendar = string.format("calendar speed %.2f, %02d:%02d", sub:GetGameSpeed(), sub:GetHour(), sub:GetMinute())
    end)
    Log(string.format("speed %dx (dilation %.2f), world clock runs %s x real, %s | %s", SPEEDS[Index],
        statics:GetGlobalTimeDilation(controller), rate, boatText, calendar))
end

-- One step on the game thread: starts at normal speed, does what the keys asked, and reports.
local function Step()
    if not Started then
        -- A reload or a loaded save must not leave the world fast. Tried again until the player exists.
        Started = Apply(1) == true
    end
    if Wanted then
        local want = Wanted
        Wanted = nil
        local before = Index
        if want == "up" then Index = math.min(Index + 1, #SPEEDS)
        elseif want == "down" then Index = math.max(Index - 1, 1)
        else Index = 1 end
        if Apply(SPEEDS[Index]) then
            Toast(string.format("Game speed %dx", SPEEDS[Index]))
        else
            Index = before
        end
    end
    if SPEEDS[Index] > 1 and os.clock() - LastReport >= TELEMETRY_S then
        LastReport = os.clock()
        pcall(Report)
    end
end

RegisterKeyBind(Key.ADD, { ModifierKey.CONTROL, ModifierKey.ALT }, function() Wanted = "up" end)
RegisterKeyBind(Key.SUBTRACT, { ModifierKey.CONTROL, ModifierKey.ALT }, function() Wanted = "down" end)
RegisterKeyBind(Key.NUM_ZERO, { ModifierKey.CONTROL, ModifierKey.ALT }, function() Wanted = "home" end)

LoopInGameThreadWithDelay(500, function()
    pcall(Step)
    return false
end)

-- A loaded save puts the speed back to normal: the world is new, and so is the speed.
pcall(function()
    NotifyOnNewObject("/Script/Engine.PlayerController", function()
        Index, Started = 1, false
    end)
end)

Log("loaded: Ctrl+Alt+Numpad + / Numpad - change the game speed (1, 2, 4, 8), Ctrl+Alt+Numpad 0 returns to normal")

if SAS_TEST then
    SasTest = {
        Step = Step, Apply = Apply, Report = Report,
        Index = function() return Index end,
        Speeds = function() return SPEEDS end,
        Press = function(name) Wanted = name end,
    }
end
