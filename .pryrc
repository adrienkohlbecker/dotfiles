# Editor for the `edit` command (vim, mvim, mate, emacsclient, ...).
Pry.config.editor = ENV.fetch('EDITOR', 'vim')

# Load Rails console helpers when running inside a Rails app. Only the
# gem-namespaced rails/console/* paths — never bare 'console_app' /
# 'console_with_helpers', which a malicious checkout could shadow from CWD.
if defined?(Rails)
  begin
    require 'rails/console/app'
    require 'rails/console/helpers'
  rescue LoadError
    warn 'pry: Rails console helpers unavailable'
  end
end

# === Listing config ===
# The default method headings are too close to the method-name colors, producing
# a "soup"; these are tuned for a Solarized terminal.
Pry.config.ls.heading_color = :magenta
Pry.config.ls.public_method_color = :green
Pry.config.ls.protected_method_color = :yellow
Pry.config.ls.private_method_color = :bright_black

# Colorized pretty-printing for all pry output via amazing_print's .ai method.
begin
  require 'amazing_print'
  Pry.config.print = proc { |output, value| output.puts value.ai }
rescue LoadError
  warn 'gem install amazing_print  # <-- highly recommended'
end
