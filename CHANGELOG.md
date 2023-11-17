# **Release v1.x.x** (TBD)

- Renamed from "neo phoenix" to "fuchsia"

## Additions

- New context menu commands:
  - `View Banner` - shows a user's banner ephemerally
  - `Steal Sticker` - attempts to steal the sticker which was included with the relevant message
- New command `/banner` shows a user's banner
- New command `/timestamp` for generating a Discord-formatted timestamp using human-readable inputs
  - Parameters accept the exact same syntax as the `when` parameter for the `/remind set` command
  - Also supports a `timezone` parameter to create absolute timestamps in any timezone
- New absolute parsing formats for `/remind set` and `/timestamp` supporting 12-hour time
- The outputs of `/todo view` and `/remind view` now have action buttons for editing and deleting the todo/reminder
- Relative times can now include months
- Reminders can now be delivered in the same channel in which the `/remind set` command was run
  - Added new `reminders_in_channel` user setting which toggles whether reminders will be delivered in their source channel by default, value defaults to `False`
  - Added new `send-here` parameter to `/remind set` which overrides user settings and toggles this option
- Implemented support for custom status
- New command `/emoji` for more conveniently creating custom emoji
  - Can steal custom emoji from other servers via the `emoji` parameter
  - Can create custom emoji from an image file using the `file` and `name` parameters

## Improvements

- Overhauled repeating reminders:
  - Only absolute reminders may repeat
  - The interval between repeating reminders can be set with a new parameter in the `/remind set` command
- Added a new `dictionary` parameter to the `/define` command which allows users to select between `standard` and `urban` dictionary, the latter searching urbandictionary.com for definitions
- Improvements to docstring formatting on commands
- Starboard no longer sends spoilered images
- `/image` command has been renamed to `/img`
- The `default_ephemeral` user setting is now `False` by default
- Updated the appearance for the outputs of `/todo list` and `/remind list`
- Increased some limits:
  - Max todos: 100 -> 1000
  - Max reminders: 15 -> 100
  - Max highlights: 10 -> 100
- Web search now shows up to 30 results
- Use new markdown in various places
- The output of the `/clear` command is now always ephemeral
- Starboard embeds now show the source channel of the starred message
- Shortened the length of the message content in a reminder delivery, embed still shows full length
- Web search embeds now show the original query
- Todo, reminder, and highlight lists are now sorted based on various criteria
- Todo and reminder list previews now strip newlines
- Shorten message content preview for highlight DMs, embed remains unaffected
- Starboard embeds now show the timestamp of the starred message's creation in the footer
- Starboard embeds now show a preview of replied-to messages if applicable
- Starboard now shows the server-specific display name and avatar of the user starred (and replied-to user if relevant)
- Replace custom absolute datetime parser with `python-dateutil` parser for much higher forgiveness with inputs

## Removals

- Removed the `/profile show` command
- Removed the `Show Message Info` context menu command
- Removed todo categories

## Fixes

- Fixed issues caused by migration to the new Discord usernames system
- Fixed an issue where if *any* channel was deleted in a server, that server's starboard channel would errofuchsiausly be set to `None`

## Other

- New `force_ephemeral` parameter for menu objects
- Improvements to autocomplete helpers
- Improved confirmations
- `DropdownMenu`s now have logic similar to the "centered" autocomplete, so that it's possible to show lists of arbitary length while respecting the option limit of 25
- Overhauled CSE module to paginate results to allow for up to 100 per query
- Elide filenames from exec command output

# **Release v1.7.1** (February 19, 2023)

## Improvements

- Ephemeral menus can now be closed manually (and will self-delete)

## Fixes

- (Internal) If an attempt to deliver a highlight to a user errors with a 403 status, that user profile's `receive_highlights` setting will automatically be set to `False` to avoid future errors
  - Also update the description of the setting to reflect this

# **Release v1.7.0** (February 19, 2023)

## Additions

- New user setting `Deliver Highlights Silently`
  - Makes use of the new notification-suppressed messages to allow highlights to configurably not send notifications (but still be delivered)

## Fixes

- Fixed clear command again such that it now works regardless of if the command was called ephemerally or not

# **Release v1.6.4** (February 13, 2023)

## Fixes

- Fixed clear command stuff

## Other

- Bump copyright year

# **Release v1.6.3** (November 25, 2022)

## Improvements

- Added new parameter help to help command output
- Added slash command signatures to help command

## Other

- Formatting & style improvements

# **Release v1.6.2** (November 21, 2022)

## Improvements

- Responses to the `View Avatar` context menu command are now always ephemeral

## Removals

- Removed the `/userinfo` command due to being unnecessary

## Fixes

- Disabled broken code in the `/todo edit` modal

# **Release v1.6.1** (July 23, 2022)

- Changes the `/info` command slightly

# **Release v1.6.0** (July 21, 2022)

## Additions

- Todos can now be moved between categories via the `/todo edit` modal (not supported on mobile yet)

## Improvements

- Updated the appearance of reminder deliveries

## Other

- Code formatting

# **Release v1.5.1** (July 17, 2022)

## Fixes

- Highlights now trigger properly once again

# **Release v1.5.0** (July 13, 2022)

## Additions

- Implemented todo categories
  - The `/todo category` subgroup has been added with commands for managing categories
  - When categories exist, new todos may optionally be added to a category upon creation (todos do not currently support being moved between categories)
  - Categories can be deleted, and users can choose to have the associated todos deleted completely, or become uncategorized
  - `/todo list` now supports an optional `category` parameter that will show only the todos that belong to a certain category

## Improvements

- Changed `ServerConfig` group display name

# **Release v1.4.0** (July 9, 2022)

## Improvements

- `settings` commands now dynamically generate autocompletions based on the setting being modified
- Content length for reminders and highlights is now validated by the Discord client, rather than the bot client

## Fixes

- Autocomplete current value for index-based commands is now clamped such that values can no longer go below 0

# **Release v1.3.1** (July 5, 2022)

## Fixes

- Fix a check error in some subcommands

# **Release v1.3.0** (July 4, 2022)

## Improvements

- `/clear` now requires the `limit` parameter
- Updated visuals for `/remind list` output

## Fixes

- Truncation of reminder content in `/remind list` is now consistent with trunction in `/todo list`

# **Release v1.2.1** (July 3, 2022)

## Fixes

- `/remind edit`'s modal now respects the maximum length of reminder content

# **Release v1.2.0** (July 3, 2022)

## Additions

- New server setting, `Allow Highlights`
  - _Currently_ `True` by default
  - If `False`, user highlights will not be triggered by messages in the server
- Reminders can now be edited just like todos
  - For now, only content can be adjusted, this may be changed in the future

## Improvements

- Updated the help message for `/help` to refer to the `default_ephemeral` field as `Private By Default`
- Rename `index` parameter to numerous commands to be more intuitive with regard to context
- Updated the unicode characters used in menu arrow buttons
- Updated button color for prompts

## Removals

- Removed the `edited` attribute from todos, which affects nothing that was ever considered relevant

## Other

- Addons now support an addon-wide interaction check, which propogates itself recursively through child groups

# **Release v1.1.4** (July 1, 2022)

## Fixes

- Use caseless comparisons when filtering certain autocomplete lists

# **Release v1.1.3** (June 30, 2022)

## Additions

- Added a `{version}` format variable to the bot activity name config entry

# **Release v1.1.2** (June 30, 2022)

- Updated library version
- Use `Interaction.app_permissions` for external emojis permission check

# **Release v1.1.1** (June 29, 2022)

## Additions

- 2 new absolute time formats for reminders
  - `%b %d` for same-year dates (like "July 5")
  - `%b %d at %H:%M` for same-year dates at a specific time (like "July 5 at 11:34")

## Fixes

- Fix absolute reminders erroring due to attempts to compare datetimes with different offset awareness

# **Release v1.1.0** (June 27, 2022)

## Additions

- Repeating reminders
  - By toggling the new `repeat` option in `/remind set`, you can mark a reminder as a repeating reminder
  - Repeating reminders will continuously remind you of the same content ad infinitum
  - The interval can be controlled through both relative and absolute termini
    - Where _n_ is the given time:
      - If relative, the reminder will be repeated once per _n_
      - If absolute, the reminder will be repeated daily at exactly _n_
    - Relative reminders must have an interval of at least 1 hour
  - Repeating reminders are marked in the reminders list with a repeat symbol
  - In the `/remind view` interface, repeating reminders will show the intervals on which they repeat

## Improvements

- The proper ellipsis character is now used in text shortening, so a bit more (2 characters) text will be shown when text is shortened

## Fixes

- Fixes a help command issue wherein whitespace was improperly stripped, causing the help command to display a difficult-to-read output on mobile devices

# **Release v1.0.1** (June 27, 2022)

- End the migration period for server configs introduced prior to v1.0.0's release

# **Release v1.0.0** (June 20, 2022)

## Breaking Changes

- With the release of major version 1.0.0, text command support has been dropped

## Additions

- Overhauled the `todo edit` command
  - When invoking the command, the previous content of the todo is now prefilled in a modal, which can now be used to edit the content without overwriting it entirely
- Updated the `choose` command
  - Now allows up to 5 different options
  - 2 options are required at minimum
- Changes to `starboard`, `server`, and `profile` settings systems
  - The settings based commands now all live under a `settings` sub-group. This means that in order to access, for example, the list of profile settings, the command will look like `/profile settings list`. This syntax holds true for all three groups

## Improvements

- The `ephemeral` param for all slash commands has been renamed to `private` to make usage more intuitive
- Invite scopes explicitly cover `bot` and `applications.commands` now
- Autocomplete for all commands which require an index has been overhauled to now provide a preview of the content of the item, as well as to center the indices "around" the current provided value so that more information is readily available
- Improvements to autocomplete for commands which accept commands as input (i.e. `help`, `server disable`)
  - `server enable` only shows commands which are currently disabled
- Setting names are now easier to understand (i.e. `default_ephemeral` now shows as `Private By Default`)

## Removals

- All old-style text commands have been removed (and are replaced by slash command versions)
- The `remind in` and `remind at` commands are removed completely, with no individual slash command replacement
  - The functionality of both is combined in `/remind set`
- Removed server setting: `prefix`

## Other

- Updated changelog style

<details>
<summary>Internal (for those who care to read it)</summary>

#### Additions

- Re-implement help command as a subclass of `AutoEphemeralAppCommand`
- Implement helper function to generate autocomplete data for index-based commands
- Implement distinct exceptions for several scenarios

#### Removals

- Removed `args` module (obsolete with full slash command implementation)
- Removed several obsolete methods from the `Fuchsia` object
- Removed `commands.HelpCommand` subclass implementation of help command
- Cleaned up unused runtime patches

#### Changes

- `Fuchsia.channel_check` and `Fuchsia.guild_disabled_check` now process only `Interaction` objects
- `Devel` command `addon` refactored to use `Literal`s rather than the now-removed `args` module
- Updated schema for todo and reminder tables (migration script included in `scripts/`)
- Refactor checks, sometimes decoupling the predicate from the check decorator, allowing predicates to be verified separately
- Overhaul settings system
  - `SETTINGS_MAPPING` dicts have been replaced by `SettingsMapping`s which contain `Setting` objects
  - `SettingsMapping`s and `Setting`s are subclasses of `Mapping` and `MutableMapping`, respectively
  - This allows the raw key names to be separated from the user-facing interfaces, by letting aliases be set and used in commands etc
- `fuchsia.classes.formatters` -> `fuchsia.tools.formatters`

#### Improvements

- Lots of typing improvements project-wide
- Various documentation improvements
</details>

# **Release v0.15.4** (June 11, 2022)

## Important

- **All** text commands<sup>1</sup> have been deprecated, and will generate an alert button whenever they are used

<sup>1</sup> Text commands that do not currently have a slash command counterpart will not generate alert buttons, because that would not make sense

## Improvements

- Both a fix and an improvement: all application command responses are now automatically deferred before their callback is invoked, which allows long-running computations to be handled without an unhelpful user-facing error showing up
- When used in ephemeral messages, menus will no longer have a `close` button, as the message can simply be dismissed

# **Release v0.15.3** (June 10, 2022)

## Fixes

- Hotfixes certain slash commands to implement `Interaction.response.defer` to allow for long-running actions to be processed without an error being shown

# **Release v0.15.2** (June 10, 2022)

## Fixes

- Implemented some changes in hopes of addressing issues with slash commands failing to respond

# **Release v0.15.1** (June 7, 2022)

## Fixes

- Group slash commands are once again properly supported in the help command

# **Release v0.15.0** (June 6, 2022)

## Additions

- Added several context menu commands:
  - For messages, a `Show Message Info` context command
  - For users, shortcuts to view the user's `userinfo` output as well as their `avatar`
- `clear` command
  - Identical to the pre-existing `purge` command in functionality
  - This command is **only** available as a slash command
    - This allows advanced options to be more easily accessible to users who, ahem, don't read the docs
    - Purge breakdowns can now be sent ephemerally, and therefore will no longer expire
- `translate` command
  - Identical to the pre-existing `translate` command, but functions solely as a slash command
- `define` command
  - Identical to the pre-existing `define` command, but functions solely as a slash command

## Improvements

- The `highlight unblock` slash command now accepts the same form of arguments as `highlight block`
- All application commands (i.e. context menu and slash) are now processed by the same global checks as classic commands. This means that:
  - <span id="disable-fix" />Commands disabled by `serversettings disable` will not be usable
  - Commands in channels ignored by `serversettings ignore` will no longer be evaluated (though an ephemeral error will be sent)
  - Global cooldowns will now be applied to application commands
- Highlights have been updated to support Discord's new Text Chat in Voice feature
- Improvements to slash command parameter naming and descriptions

## Fixes

- The help documentation for `remind set` has been corrected
- Related to [app commands global check processing](#disable-fix), commands are now properly blocked by server rules
- Fixes wrapped converters failing to convert

## Other

- The entire source has been (loosely) typed - not yet strictly typed
- Code for patching the `ephemeral` parameter to all slash commands has been extended to support all variants of slash commands
- Added a `deprecate` decorator to facilitate marking functions as deprecated
  - The help command takes advantage of this to display deprecated commands as well
  - Deprecated commands will have a button in their output which alerts the user of the command's deprecation status
- Old-style commands marked as deprecated:
  - `remind at`
  - `remind in`
  - `translate`
  - `purge`
  - `define`
- Reminders are now checked via batch polling rather than async wait tasks for each individual reminder

# **Release v0.14.0** (May 21, 2022)

## Initial Slash Commands

- fuchsia phoenix has been updated to support slash commands
  - Support is currently limited to several commands
  - More commands should become slash commands as time progresses
- To accomodate some code limitations in having commands function as both text and slash commands, the inputs for several commands has been changed slightly:
  - `highlight remove`, `todo remove`, and `remind cancel` no longer accept more than one index at once
    - `~` is still a valid input to any of these commands
  - The functionality for `highlight block` has been separated into two logical subcommands: `highlight block` and `highlight blocklist`
    - `highlight block` accepts a single argument (if text command) or multiple (if slash command) to block from highlighting
    - `highlight blocklist` takes no arguments and sends the blocklist
- All slash commands offer an `ephemeral` option, which controls whether or not others will be able to view your command output
- A list of commands that currently support slash commands:
  - `highlight` (whole group)
  - `help`
  - `google` and `image`
  - `avatar`
  - `userinfo`
  - `serverinfo`
  - `roleinfo`
  - `info`
  - `profilesettings` (whole group)
  - `profile` (whole group)
    - Original main command functionality has been moved to `profile show`
  - `todo` (whole group)
  - `serversettings` (whole group)
  - `starboard` (whole group)
  - `remind` (whole group\*)
    - The `remind in` and `remind on` subcommands do not have slash command analogs  
      Instead, the functionality exists under `remind set`, a slash-command exclusive command  
      `remind set` uses slash command features to more intuitively interpret input

## Additions

- Added brand new system for managing settings for `Profile`, `Server`, and `Starboard`, making use of the new Discord modal interaction
  - Introduces new options on the main settings lists for setting and resetting the currently displayed setting
  - Currently, the previously-existing `set` and `reset` commands-based system will not be affected, as it is still necessary for easily controlling options such as starboard emotes
- Added a new user setting, `default_ephemeral`, to complement the implementation of slash commands
  - This setting controls whether slash commands will be responded to ephemerally by default or not
  - The default value is `True`
  - This setting will always be overridden if the `ephemeral` parameter is passed to any slash command

## Improvements

- Commands (and all associated subcommands) are now case-insensitive

## Fixes

- Fixed a regression in query handling for the `image` shortcut command which was causing inputs to inexplicably fail to return the proper results

# **Release v0.13.0** (Janurary 24, 2022)

## Additions

- `serversettings disable`/`serversettings reenable` system
  - Allows server administrators to disable fuchsia phoenix's commands within their server
  - Disabled commands will not be acknowledged, unless invoked by administrators
  - Running `serversettings disable` with no arguments will display a list of all currently ignored commands
- `choose` command
  - Given a set of choices, makes a (pseudo-) random selection and outputs the results
  - Can be provided a comma-separated list of options to randomize

## Improvements

- Adjusted the design of the output of `starboard ignored` to be consistent with other listings
- `remind view` now provides a jump URL to the reminder's origin - note: this may not work if the message has been deleted
- Highlights will now work in private threads. Highlights will only be delivered if they highlighted user is a member of the private thread
- Redesigned appearance for starred messages
- Minute changes to highlight messages (added a button to jump to the trigger message)

## Fixes

- Fixed an issue wherein invoking `userinfo` on a verified bot would fail to display the account's username and discriminator
- Fixed an issue where errors would be produced when a channel is deleted in a server without a starboard

## Other

- Updated startup code to have manual control over the event loop

# **Release v0.12.1** (November 1, 2021)

## Improvements

- Adjust Unicode characters used for menu paging buttons
- Adjusted the display of command aliases in flag command help
- Adjusted behavior of starboard's `max_days` setting to match its description
  - Messages older than the `max_days` will now:
    - Not be sent to starboard as new stars (no change)
    - If they already have a corresponding star, that star will still be updated (adjusted behavior)
- Improved clarity of `starboard ignore`/`starboard unignore` error messages
- Show flag argument defaults in command help
- Rename `Aliases` to `Command Aliases` and flag aliases from `Aliases` to `Flag Aliases` for clarity

## Other

- Updated to Python 3.10
  - Updated some syntax accordingly

# **Release v0.12.0** (October 3, 2021)

## Additions

- `roleinfo`/`ri` command
  - Displays relevant information pertaining to the given role
  - Can only be used in servers
- `serversettings ignore`/`serversettings unignore` system
  - Enables server administrators to specify channels in which command invocation will not be acknowledged
  - Ignored channels will not respond to commands, unless invoked by administrators (to prevent accidentally disabling all channels)
  - Running `serversettings ignore` with no arguments will display a list of all currently ignored channels
- `purge`/`clear`/`c` command
  - Purges a variable number of messages from the channel in which it is invoked
  - Restrictions:
    - Invoking member must have `manage_messages` channel permission
    - fuchsia phoenix must have `manage_messages` channel permission
    - Command may only be invoked within a server
  - Flag command to allow for powerful specification:
    - `--after` and `--before` flag to purge within certain timeframes
    - `--user` flag to only purge messages from select users
      - Adding the `--user` flag multiple times allows for multiple users to be selected at once
    - `limit` positional argument to control how many messages are purged at once
  - Sends a breakdown of number of messages deleted per member after completition, which then deletes itself after 10 seconds

## Improvements

- Contextual embeds from highlights will now replace all custom emoji with the `❔` character
- Standardized appearance of `hl block` list embed
- Slightly redesigned appearance of flag descriptions in flag command help
- Rewrote starboard caching logic:
  - Stars are now cached on-demand, rather than upfront
  - Cached stars are invalidated after 5 minutes of not being modified
  - Added graceful handler for the deletion of starboard channels

## Fixes

- Fixed an edge case in highlights whereby, if a message event was received prior to the bot's internal cache being ready, the highlights cache would be computed incorrectly, causing all highlights to fail to be cached, thus preventing any highlights from being delivered

# **Release v0.11.1** (September 16, 2021)

## Fixes

- `avatar` now properly fetches guild members when applicable
- Updated the description for the `remind in` command

# **Release v0.11.0** (August 26, 2021)

Release v0.11.0 standardizes certain interfaces, adds some new feature support, plus some various other changes.

## Improvements

- `avatar` command now supports per-guild avatars where applicable
  - In cases where one is found, the embed sent will have both the global and guild avatars as the image and thumbnail, respectively
  - Embeds also feature a button to swap the image and the embed
- Renamed `settings` and `server` commands to `profilesettings` and `serversettings`, respectively
  - Previous names are currently present as aliases for backwards-compatability
- Standardize subcommand interfaces for `highlight`, `todo`, `profilesettings`, `serversettings`, `starboard`, and `remind` command groups
  - Previous behavior: calling any of these parent commands with no arguments or subcommands would:
    - Display a list of associated items
    - Allow the scheduling of a relative reminder (`remind` group only)
  - New behavior: calling any parent command by itself will do **nothing**
    - Previous behavior has been moved to an appropriate subcommand:
      - Associated items may be accessed via the `<command> *list*` invocation
      - Relative reminders are scheduled via the `remind in` subcommand
- Add `remove`, `rm` aliases to `remind cancel` for consistency purposes
- Dropdown menus now make full use of the extended character limits of select menus

## Fixes

- Absolute reminders now properly detect if the scheduled time is within the current day or not, based on timezone

## Other

- Runtime patches have been relocated to `runtime.py`
- Unnecessary runtime patches have been removed

# **Release v0.10.3** (July 28, 2021)

## Fixes

- Fix issues with ignoring entities from a starboard
- Fix highlights not being compiled as case-insensitive
- Implement potential fix for issues with invite dropdown failing to respond

## Other

- Implement event system separate from `discord.Client.dispatch` due to volatility of that API

# **Release v0.10.2** (July 26, 2021)

## Fixes

- Fix an AttributeError when setting a starboard channel (was caused due to residual code)

# **Release v0.10.1** (July 25, 2021)

## Fixes

- Fix an unintentionally public IndexError

# **Release v0.10.0** (July 23, 2021)

Release v0.10.0 implements a couple of utility commands.

## Additions

- `serverinfo`/`si` command
  - Displays relevant information pertaining to the current guild
- `translate`/`tr` command
  - Translates text across languages via the Google Translate API
  - Supports a directive-based specification for controlling source and destination languages

## Improvements

- Demote `command_error` errors to `warn` logging level
- Added `support`, `source`, and `privacy` aliases to the `info` command
- Reworked functionality of `exec` command and backend
  - Notably, solved the recursion that was previously present in the `scope`
- Logically partitioned `requirements.txt`

# **Release v0.9.3** (July 22, 2021)

## Improvements

- Rename `eval` command to `exec`
- Remove extrafuchsiaus `Starboard` attributes
- Change type of `Starboard.ignored`

# **Release v0.9.2** (July 21, 2021)

## Fixes

- Fixed an issue with reminders occasionally wrongly displaying "[source deleted]" when delivered in direct messages

# **Release v0.9.1** (July 20, 2021)

0.9.1 fixes issues found in 0.9.0 and earlier.

## Improvements

- Removed an extrafuchsiaus attribute from starboard objects

## Fixes

- When sending messages in a channel is impossible, the error is logged and ignored silently
- Fixed parameter issues in `on_error`
- Fixed mobile formatting regression with ephemeral privacy policy

# **Release v0.9.0** (July 17, 2021)

Release v0.9.0 cleans up and slightly enhances fuchsia phoenix.

## Legal

- Revised privacy policy

## Improvements

- Highlight context now displays _around_ the trigger message. This means that up to 3 earlier and up to 3 later messages will be displayed
- The collection mechanism for highlight has been improved
- The invite URL is now displayed as an inline hyperlink
- All icons have been refreshed
- Pass for documentation, improving clarity where it may have been lacking

## Other

- Optimizations for profile code

# **Release v0.8.0** (July 8, 2021)

This release is mostly comprised of polish for existing features.

## Legal

- Updated privacy policy (made public in repository, rewrote for better clarity)
- Licensed project under the GNU Affero General Public License v3.0 (AGPLv3)

## Improvements

- Reworked menus for several commands (`help`, `google`, `define`) to supply dropdown menus, making it easier to quickly access a page
- Tweaked the buttons for and added an `invite` alias to the `info` command
- Command aliases are now displayed in that command's help embed
- Shortened the `star_format` starboard option to `format`

## Fixes

- Fixed an issue with unicode starboard emojis that caused incorrect validation, and prevented stars from registering
- Fixed the behavior of index chaining in the `remind cancel` command
- Fixed the help command behaving incorrectly because of the global cooldown

## Other

- Optimization:
  - Remove `bot.get_server` and `bot.get_profile` in favor of accessing the attribute directly or using `__contains__` for membership checks (sidesteps lookup overhead)
  - Where it is known that a value will always exist, direct `__getitem__` access is used instead of `dict.get`, which shaves off further attribute lookup
  - Restricted gateway intents to only the required ones, rather than using the defaults
  - Optimize starboard with `__getitem__` rather than `dict.get` (where appropriate)
  - Implement `__slots__` in far more locations, significantly reducing memory footprint
- Implement maximum number of todos (100)
- Revised internal terminology for server configs:
  - Dropped use of "`server`" in backend
  - Anything that was previously referred to as a "`server`" has been labelled as a "`config`"/"`guild config`"
  - Note that these changes are internal only, and that frontend interfaces all still refer to `config`s as `server`s
- Rework `modules.paginator`:
  - Rename module to `modules.menus`
  - Rework `Paginator` object to function as a subclass of `discord.ui.View`
  - Implement a `DropdownMenu` for creating menus that can be paged via both buttons or a dropdown menu (support up to 25 items)
  - `Pages` now supports a `template_embed` keyword-only argument, for defining a static template embed that is merged with the `Pages` object's content

# **Release v0.7.0** (July 2, 2021)

In large part, this release extends and improves existing features.

## Improvements

- Highlights have been updated to work with Discord's upcoming threads feature
  - A thread's parent channel permissions are checked to confirm if a user can receive highlights from a given public thread
  - Highlights will **never** be triggered by private threads, regardless of permissions
- Stickers will now be listed in highlight embeds in the same way images and embeds are shown
- Indexing for list-based interfaces now begins at `1`
  - This affects interfaces including highlights, and todos
- Implemented index chaining and the `~` operator for the `highlight remove` command
- Shortened the `starboard_enabled` server config key to `starboard`
- `avatar` command now uses a `MemberConverter` as a conversion strategy, enabling lookup by display/user name
- `info` command now uses persistent views, so its buttons can be utilized indefinitely

## Additions

- Added `Support Server` button to `info` command output
  - Added corresponding key to config file, along with key for configuring whether the button is enabled or not
- Overhauled flow of `Invite fuchsia phoenix` button on the `info` command
  - Responds ephemerally now
  - Uses dropdown menus to allow users to select permission presets for inviting fuchsia phoenix

## Other

- Added `uvloop` as a conditional dependency for `linux` systems, improving `asyncio` performance
- Updated default name for auto-generated config templates, and added a comment to the top of auto-generated files

# **Release v0.6.0** (June 25, 2021)

This release fleshes out fuchsia phoenix's feature set further.

## Highlight Collection

- As of v0.6.0, highlights are delivered via a "collection" method
- A periodic timer triggers highlight delivery every 5 seconds
  - Highlight context embeds aren't generated until delivery time, rather than at the instant of being triggered
- Any highlights triggered in a given channel within the 5 second period will be collected into a single highlight notification, rather than delivering an individual message for each highlight (the latter is the behavior of legacy `fuchsia` highlights)

## Other

- Implemented a developer `addon` command for loading, unloading, and reloading fuchsia phoenix addons post-runtime
- Implemented a `PeriodicTimer` class to support the highlight collection feature
  - Also added an accompanying decorator to simplify the creation of timers

# **Release v0.5.0** (June 24, 2021)

This release implements features to bring fuchsia phoenix closer to a stable 1.0.0 release.

## Front-End Changes/Additions

- Implemented a bot info command, `info`
  - Includes version info, uptime, relevant links, and a button to display privacy information
  - Privacy information describes in greater detail how timezone data will be used
- Exceptions are now displays in their `__str__` representation, rather than their `__repr__`, providing a more user-friendly experience when errors are raised
- Additionally, added a list of ignored exceptions, so that more obstructive exceptions don't send messages
- To avoid usability regressions, an `image` command has been added as a shortcut for invoking `google --image`
- Renamed the `server init` and `profile init` commands to `server create` and `profile create`, for a more straightforward usage

## Back-End Changes/Additions

- All logging now uses ANSI escapes to add color to messages
- Added a script `config_gen.py` for automatically generating example config files from a real config file
- Changed converters from `commands.Converter` subclasses to standalone functions
- Resolved an issue causing starboards to behave improperly when their emoji setting was changed

# **Release v0.4.0** (June 22, 2021)

## Reminders

This release implements a full `Reminders` system.

Below is a comparison between the system's predecessor (legacy `fuchsia` `Reminders`) and the new implementation.

#### Similarities to predecessor:

- Front-facing interface aims to be as familiar as possible
- Provides the capability to schedule reminders from both relative offsets, and absolute datetimes
- Implements the same basic functions `remind list`, `remind cancel`
- Implements a similar fallback hierarchy for reminder deliver (reply to invocation message -> mention user in channel of invocation -> send user a direct message with content -> fail silently)
- Reminders can still be scheduled from within a server, or from a direct message

#### Differences from predecessor:

- Separates reminder scheduling into 2 separate commands, one for relative offsets, the other for absolute datetimes
  - Relative offset scheduling is assigned to the parent group `remind`
  - Absolute datetime scheduling is assigned to the subcommand `remind [on/at]`
    - Naming aims to be as conducive to natural datetime expression as possible (`remind on June 7, 20XX Do something`)
- Implements subcommand `remind [view/show]` for viewing the full content of a reminder (reminder content is truncated to 50 characters in the list view)
- Both relative offset and absolute datetime scheduling are built from lightweight parsers that take advantage of strict bounds on allowed inputs
  - Parsing also now allows for the actual content of a reminder to be separated from its deadline (both relative and absolute, unlike legacy `fuchsia` reminders which only separated content from absolutes)
  - Strict parsing allows for more informative documentation, along with examples, increasing ease of use versus legacy `fuchsia` reminders
- Implements a maximum number of reminders (15 as of initial release)
- Increased maximum length for reminder content (1,000 versus legacy `fuchsia`'s 200)
- Implements implied localization for users who have configured a timezone in their profile
  - Absolute datetimes _only_ will be constructed with a user's configured timezone
  - Absolute datetimes for users without a configured timezone will mirror legacy `fuchsia`'s use of UTC
- Reminders are linked to a user's profile via `FOREIGN KEY`, versus the free-standing structure of legacy `fuchsia` reminders
  - Users are required to have initialized a profile in order to access the reminder interface
  - This change allows for both increased consistency for users, and creates a more connected structure for the database

## Other Changes

- User setting `hl_timeout` has been implemented, introducing the ability to customize the duration of time for which a user must be absent from a channel for them to be considered "inactive", and thus, able to receive highlights
  - Value is set in minutes, with the default being 1, and having a constraint of `>= 1 AND <= 5`
- Implement developer command `sql` for streamlined database interfacing
  - Depends on new `Table` class for formatting entries into an optimally readable form

# **Release v0.3.1** (June 20, 2021)

- Fixed an issue with `Starboard` editing brand-new stars upon creation

# **Release v0.3.0** (June 20, 2021)

This release mainly targets the profile system, and improves upon it significantly.

- Renamed `user_settings` extension to `profile`
- Implemented command group `profile`, which shows information pertaining to the specified user's profile (provided they have a profile, otherwise exiting)
- Implemented commands for:
  - Creating a user profile, `profile init`, which creates a base profile
  - Deleting a user profile, `profile delete`, which deletes a user profile, also deleting all associated data (todos, highlights, ...) via cascade
- Implemented a custom `Context`
  - Implemented a prompt method on this, allowing for interactive prompting of users
- Implemented a `reset` subcommand on both `server` and `settings` groups
  - This command resets an option to the default that is provided in the database
- Expanded upon data stored in a user profile
  - Added `created_at`, which stores the timestamp of the account's creation
  - Added `timezone`, which stores a user's timezone
    - This is entirely opt-in
    - By setting this value (via the `settings set` command), the user acknowledges the ways in which their timezone will be used (as is explicitly laid out in the documentation for the field)
    - Being a profile setting, this can be reset by the user at any point via the `settings reset` command

# **Release v0.2.1** (June 20, 2021)

- Addresses minor bugs in `Starboard`
- Implements a command to manually initialize a server's config entry if, for some reason, it is not automatically generated (which it is not, yet)

# **Release v0.2.0** (June 19, 2021)

This release implements the `Starboard` feature, and its full functionality. It functions largely identically to its predecessor, with several key improvements:

- Management of starboard settings has been consolidated to a single, extensible system, utilizing SQL comments for logical, standardized documentation
- fuchsia phoenix's starboard features the ability to ignore/unignore message and channel IDs, preventing them from reaching starboard
- Code style and fluency has also been improved all-around

# **Release v0.1.0** (June 6, 2021)

- Includes a reasonable amount of initial features
- Introduces various frameworks for convenience

_Note: Ideally, this release could have been released alongside the initial commit, but that didn't happen. Releases will follow commits more closely going forward._
