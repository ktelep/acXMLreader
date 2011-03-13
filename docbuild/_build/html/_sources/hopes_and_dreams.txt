Future Plans for Project
========================
This started as a pretty basic script, but has evolved into a todo list of what it should be (and can be) by following some basic Python concepts.

* Needs to be 'modulized' 

  * Currently runs start to end
  * Grossly not reusable code
  * See if we can genericize it to the point we can use it for CCC also?

* Actually handle different schema versions from EMC

* Support more tags

  * Add support for tags that I'm currently ignoring
  * Later versions of code magically have more tags appearing for

    # Virtualization devices
    # Replication tags

* Possibly remove dependency on SQLAlchemy

  * Just create a standard datastructure
  * But provide the compatibility to dump back into SQL
