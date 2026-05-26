# Editor for the `edit` command (vim, mvim, mate, emacsclient, ...).
Pry.config.editor = 'vim'

# Load Rails console helpers when running inside a Rails app.
if defined?(Rails)
  begin
    require 'rails/console/app'
    require 'rails/console/helpers'
  rescue LoadError
    require 'console_app'
    require 'console_with_helpers'
  end
end

# === Listing config ===
# The default method headings are too close to the method-name colors, producing
# a "soup"; these are tuned for a Solarized terminal.
Pry.config.ls.heading_color = :magenta
Pry.config.ls.public_method_color = :green
Pry.config.ls.protected_method_color = :yellow
Pry.config.ls.private_method_color = :bright_black

# awesome_print: colorized pretty-printing for all pry output, when available.
begin
  require 'awesome_print'
  Pry.config.print = proc { |output, value| output.puts value.ai }
rescue LoadError
  puts 'gem install awesome_print  # <-- highly recommended'
end
